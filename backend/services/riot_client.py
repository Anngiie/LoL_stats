"""
LoL Stats - Riot Games API Client
==================================
Rate-limited HTTP client for the Riot Games REST API.

Handles:
  - Token-bucket rate limiting (20 req/s, 100 req/2min for dev keys)
  - Automatic retry on 429 (Rate Limit Exceeded) with exponential backoff
  - Error handling (403 = expired key, 404 = not found)
  - Riot ID → PUUID lookup via Account-V1
  - Match history and match detail endpoints
"""

import logging
import time
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Riot API base URLs
PLATFORM_ROUTING = {
    "euw1": "europe", "eun1": "europe", "ru": "europe", "tr1": "europe",
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr": "asia", "jp1": "asia", "sg2": "sea", "tw2": "sea", "vn2": "sea",
    "oc1": "sea", "ph2": "sea", "th2": "sea",
}
REGIONAL_BASE = "https://{routing}.api.riotgames.com"

# DataDragon for static data (no API key needed)
DATADRAGON_BASE = "https://ddragon.leagueoflegends.com"


class RateLimiter:
    """
    Token-bucket rate limiter supporting two windows:
      - Short: 20 requests per second (Riot dev key)
      - Long:  100 requests per 2 minutes (Riot dev key)
    Thread-safe.
    """

    def __init__(self, per_second: int = 19, per_2min: int = 95) -> None:
        self._short_max = per_second
        self._long_max = per_2min
        self._short_tokens = float(per_second)
        self._long_tokens = float(per_2min)
        self._short_window = 1.0  # seconds
        self._long_window = 120.0  # seconds
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._short_tokens = min(
            self._short_max,
            self._short_tokens + elapsed * (self._short_max / self._short_window),
        )
        self._long_tokens = min(
            self._long_max,
            self._long_tokens + elapsed * (self._long_max / self._long_window),
        )

    def acquire(self) -> float:
        """
        Wait until a token is available and consume it.
        Returns the wait time in seconds (0 if no wait needed).
        """
        with self._lock:
            self._refill()
            if self._short_tokens >= 1 and self._long_tokens >= 1:
                self._short_tokens -= 1
                self._long_tokens -= 1
                return 0.0

            # Calculate how long to wait
            short_wait = (
                (1 - self._short_tokens)
                * self._short_window
                / self._short_max
            )
            long_wait = (
                (1 - self._long_tokens)
                * self._long_window
                / self._long_max
            )
            wait = max(short_wait, long_wait)
            logger.debug("Rate limiter waiting %.2fs", wait)
            time.sleep(wait)
            self._refill()
            self._short_tokens -= 1
            self._long_tokens -= 1
            return wait


class RiotClient:
    """
    HTTP client for the Riot Games API with rate limiting and error handling.
    """

    def __init__(
        self,
        api_key: str,
        per_second: int = 19,
        per_2min: int = 95,
    ) -> None:
        self._api_key = api_key
        self._limiter = RateLimiter(per_second, per_2min)
        self._session = requests.Session()
        self._session.headers.update(
            {"X-Riot-Token": self._api_key}
        )

    @property
    def has_key(self) -> bool:
        return bool(self._api_key)

    # ─── Core request method ──────────────────────────────────

    def _request(
        self,
        url: str,
        params: Optional[dict] = None,
        retries: int = 3,
    ) -> Optional[dict]:
        """
        Make a rate-limited GET request to the Riot API.
        Returns parsed JSON dict, or None on non-retryable errors.

        Args:
            url: Full API URL.
            params: Optional query parameters.
            retries: Max retries on 429/5xx errors.
        """
        if not self._api_key:
            logger.error("No Riot API key configured.")
            return None

        for attempt in range(retries):
            self._limiter.acquire()

            try:
                resp = self._session.get(url, params=params, timeout=15)
            except requests.RequestException as e:
                logger.error("Request failed (attempt %d/%d): %s", attempt + 1, retries, e)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                # Rate limit — use Retry-After header or exponential backoff
                retry_after = resp.headers.get("Retry-After", "2")
                try:
                    wait = int(retry_after)
                except ValueError:
                    wait = 2 ** attempt
                logger.warning("Rate limited (429), waiting %ds...", wait)
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                logger.error("Riot API returned 403 — API key may be expired or invalid.")
                return None

            if resp.status_code == 404:
                logger.debug("Riot API returned 404 for: %s", url)
                return None

            if resp.status_code >= 500:
                logger.warning("Riot API server error %d, retrying...", resp.status_code)
                time.sleep(2 ** attempt)
                continue

            logger.error("Unexpected status %d for: %s", resp.status_code, url)
            return None

        logger.error("Request failed after %d retries: %s", retries, url)
        return None

    # ─── Routing helpers ─────────────────────────────────────

    def _regional_base(self, region: str) -> str:
        routing = PLATFORM_ROUTING.get(region.lower(), "europe")
        return REGIONAL_BASE.format(routing=routing)

    def _platform_base(self, region: str) -> str:
        return f"https://{region.lower()}.api.riotgames.com"

    # ─── Account-V1 (Riot ID → PUUID) ────────────────────────

    def get_puuid(self, game_name: str, tag_line: str, region: str = "euw1") -> Optional[str]:
        """
        Resolve a Riot ID (game_name#tag_line) to a PUUID.

        Args:
            game_name: Riot ID game name.
            tag_line: Riot ID tag line (without #).
            region: Platform region for routing (e.g. 'euw1', 'na1').

        Returns:
            PUUID string or None if not found.
        """
        base = self._regional_base(region)
        url = f"{base}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        data = self._request(url)
        if data:
            return data.get("puuid")
        return None

    def get_account(self, puuid: str, region: str = "euw1") -> Optional[dict]:
        """Get account info by PUUID."""
        base = self._regional_base(region)
        url = f"{base}/riot/account/v1/accounts/by-puuid/{puuid}"
        return self._request(url)

    # ─── Summoner-V4 ─────────────────────────────────────────

    def get_summoner(self, puuid: str, region: str) -> Optional[dict]:
        """Get summoner profile by PUUID (level, icon, etc.)."""
        base = self._platform_base(region)
        url = f"{base}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return self._request(url)

    # ─── Match-V5 ────────────────────────────────────────────

    def get_match_ids(
        self,
        puuid: str,
        region: str = "euw1",
        count: int = 20,
        start: int = 0,
        queue: Optional[int] = None,
    ) -> list[str]:
        """
        Get a list of match IDs for a summoner.

        Args:
            puuid: The summoner's PUUID.
            region: Platform region for routing.
            count: Number of matches to fetch (max 100).
            start: Offset for pagination.
            queue: Optional queue filter (420 = ranked solo, 440 = flex, 450 = ARAM).

        Returns:
            List of match ID strings.
        """
        base = self._regional_base(region)
        url = f"{base}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {"count": min(count, 100), "start": start}
        if queue is not None:
            params["queue"] = queue
        data = self._request(url, params=params)
        return data if data else []

    def get_match(self, match_id: str, region: str = "euw1") -> Optional[dict]:
        """Get full match detail by match ID."""
        base = self._regional_base(region)
        url = f"{base}/lol/match/v5/matches/{match_id}"
        return self._request(url)

    # ─── League-V4 ───────────────────────────────────────────

    def get_ranked_entries(self, summoner_id: str, region: str) -> Optional[list[dict]]:
        """Get all ranked entries for a summoner."""
        base = self._platform_base(region)
        url = f"{base}/lol/league/v4/entries/by-summoner/{summoner_id}"
        return self._request(url)


# ─── DataDragon (static data, no API key needed) ─────────────────

_datadragon_session = requests.Session()


def get_latest_version() -> Optional[str]:
    """Get the latest DataDragon game version (e.g. '14.10.1')."""
    try:
        resp = _datadragon_session.get(
            "https://ddragon.leagueoflegends.com/api/versions.json",
            timeout=10,
        )
        resp.raise_for_status()
        versions = resp.json()
        return versions[0] if versions else None
    except Exception as e:
        logger.warning("Failed to fetch DataDragon version: %s", e)
        return None


def get_champion_data(version: Optional[str] = None) -> Optional[dict]:
    """
    Get champion name → ID mapping and basic info from DataDragon.

    Returns dict with keys: 'data' (champion_name -> {id, name, title, ...})
    """
    if not version:
        version = get_latest_version()
    if not version:
        return None

    try:
        resp = _datadragon_session.get(
            f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json",
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Failed to fetch champion data: %s", e)
        return None

"""
LoL Stats - Database Layer
===========================
SQLite connection management and schema initialization.

Uses raw sqlite3 (no ORM) for simplicity — the schema is small and
stable. A thin Database class wraps the connection with context-manager
support for transactions.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS summoners (
    puuid           TEXT PRIMARY KEY,
    game_name       TEXT NOT NULL,
    tag_line        TEXT NOT NULL,
    profile_icon_id INTEGER DEFAULT 0,
    summoner_level  INTEGER DEFAULT 0,
    region          TEXT NOT NULL,
    rank_tier       TEXT DEFAULT '',
    last_updated    TEXT NOT NULL DEFAULT (datetime('now')),
    is_tracked      INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    match_id        TEXT PRIMARY KEY,
    puuid           TEXT NOT NULL,

    -- Match metadata
    game_creation   INTEGER NOT NULL,
    game_duration   INTEGER NOT NULL,
    game_version    TEXT,
    queue_id        INTEGER,
    platform_id     TEXT,

    -- Participant info
    champion_id     INTEGER NOT NULL,
    champion_name   TEXT NOT NULL,
    individual_position TEXT,
    team_id         INTEGER,
    win             INTEGER NOT NULL,

    -- Core stats
    kills           INTEGER DEFAULT 0,
    deaths          INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,

    -- Damage
    total_damage_dealt_to_champions   INTEGER DEFAULT 0,
    total_damage_taken                INTEGER DEFAULT 0,

    -- Gold / CS
    gold_earned         INTEGER DEFAULT 0,
    total_minions_killed   INTEGER DEFAULT 0,
    neutral_minions_killed INTEGER DEFAULT 0,

    -- Vision
    vision_score            INTEGER DEFAULT 0,
    vision_wards_bought     INTEGER DEFAULT 0,
    wards_placed            INTEGER DEFAULT 0,
    wards_killed            INTEGER DEFAULT 0,
    control_wards_placed    INTEGER DEFAULT 0,

    -- Items (0-6, where 6 is trinket)
    item0 INTEGER DEFAULT 0,
    item1 INTEGER DEFAULT 0,
    item2 INTEGER DEFAULT 0,
    item3 INTEGER DEFAULT 0,
    item4 INTEGER DEFAULT 0,
    item5 INTEGER DEFAULT 0,
    item6 INTEGER DEFAULT 0,

    -- Summoner spells / runes
    summoner1_id  INTEGER DEFAULT 0,
    summoner2_id  INTEGER DEFAULT 0,
    perk_primary_style    INTEGER DEFAULT 0,
    perk_sub_style        INTEGER DEFAULT 0,

    -- Champion-specific stats
    champ_level          INTEGER DEFAULT 0,
    champ_experience     INTEGER DEFAULT 0,

    -- Multikills
    double_kills   INTEGER DEFAULT 0,
    triple_kills   INTEGER DEFAULT 0,
    quadra_kills   INTEGER DEFAULT 0,
    penta_kills    INTEGER DEFAULT 0,

    -- Objectives
    turret_kills          INTEGER DEFAULT 0,
    inhibitor_kills       INTEGER DEFAULT 0,
    dragon_kills          INTEGER DEFAULT 0,
    baron_kills           INTEGER DEFAULT 0,

    -- Team / lane context (populated at parse time)
    team_kills              INTEGER DEFAULT 0,
    lane_partner_champion   TEXT DEFAULT '',

    -- Derived analysis (pre-computed JSON)
    analysis_data   TEXT,

    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (puuid) REFERENCES summoners(puuid)
);

CREATE INDEX IF NOT EXISTS idx_matches_puuid ON matches(puuid);
CREATE INDEX IF NOT EXISTS idx_matches_game_creation ON matches(game_creation DESC);
"""


class Database:
    """Thin wrapper around a sqlite3 connection."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path

    # ── Connection management ──

    def get_connection(self) -> sqlite3.Connection:
        """Get a new connection (caller is responsible for closing it)."""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single statement with auto-commit."""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a statement for each param set in a single transaction."""
        with self.get_connection() as conn:
            conn.executemany(sql, params_list)
            conn.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row or None."""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all matching rows."""
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    # ── Schema ──

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        self._migrate()
        logger.info("Database initialized at %s", self._path)

    def _migrate(self) -> None:
        """Add columns that were introduced after the initial schema."""
        match_migrations = [
            ("team_kills", "INTEGER DEFAULT 0"),
            ("lane_partner_champion", "TEXT DEFAULT ''"),
        ]
        summoner_migrations = [
            ("rank_tier", "TEXT DEFAULT ''"),
        ]
        with self.get_connection() as conn:
            existing_matches = {row[1] for row in conn.execute("PRAGMA table_info(matches)")}
            for col_name, col_type in match_migrations:
                if col_name not in existing_matches:
                    conn.execute(
                        f"ALTER TABLE matches ADD COLUMN {col_name} {col_type}"
                    )
                    logger.info("Migrated: added column %s to matches", col_name)

            existing_summoners = {row[1] for row in conn.execute("PRAGMA table_info(summoners)")}
            for col_name, col_type in summoner_migrations:
                if col_name not in existing_summoners:
                    conn.execute(
                        f"ALTER TABLE summoners ADD COLUMN {col_name} {col_type}"
                    )
                    logger.info("Migrated: added column %s to summoners", col_name)
            conn.commit()

    # ── Summoner helpers ──

    def upsert_summoner(
        self,
        puuid: str,
        game_name: str,
        tag_line: str,
        region: str,
        profile_icon_id: int = 0,
        summoner_level: int = 0,
        rank_tier: str = "",
    ) -> None:
        """Insert or update a summoner record."""
        self.execute(
            """
            INSERT INTO summoners (puuid, game_name, tag_line, region, profile_icon_id, summoner_level, rank_tier, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(puuid) DO UPDATE SET
                game_name = excluded.game_name,
                tag_line = excluded.tag_line,
                region = excluded.region,
                profile_icon_id = excluded.profile_icon_id,
                summoner_level = excluded.summoner_level,
                rank_tier = excluded.rank_tier,
                last_updated = datetime('now')
            """,
            (puuid, game_name, tag_line, region, profile_icon_id, summoner_level, rank_tier),
        )

    def summoner_exists(self, puuid: str) -> bool:
        """Check if a summoner is already in the database."""
        row = self.fetch_one("SELECT 1 FROM summoners WHERE puuid = ?", (puuid,))
        return row is not None

    def match_exists(self, match_id: str) -> bool:
        """Check if a match is already stored."""
        row = self.fetch_one("SELECT 1 FROM matches WHERE match_id = ?", (match_id,))
        return row is not None

    def insert_match(self, match_data: dict) -> None:
        """Insert a full match record from a parsed Riot API response."""
        cols = [
            "match_id", "puuid", "game_creation", "game_duration", "game_version",
            "queue_id", "platform_id", "champion_id", "champion_name",
            "individual_position", "team_id", "win",
            "kills", "deaths", "assists",
            "total_damage_dealt_to_champions", "total_damage_taken",
            "gold_earned", "total_minions_killed", "neutral_minions_killed",
            "vision_score", "vision_wards_bought", "wards_placed",
            "wards_killed", "control_wards_placed",
            "item0", "item1", "item2", "item3", "item4", "item5", "item6",
            "summoner1_id", "summoner2_id", "perk_primary_style", "perk_sub_style",
            "champ_level", "champ_experience",
            "double_kills", "triple_kills", "quadra_kills", "penta_kills",
            "turret_kills", "inhibitor_kills", "dragon_kills", "baron_kills",
            "team_kills", "lane_partner_champion",
        ]
        placeholders = ", ".join("?" * len(cols))
        values = tuple(match_data.get(c, 0) for c in cols)
        self.execute(
            f"INSERT OR REPLACE INTO matches ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )

    def update_match_analysis(self, match_id: str, analysis_json: str) -> None:
        """Store pre-computed analysis for a match."""
        self.execute(
            "UPDATE matches SET analysis_data = ? WHERE match_id = ?",
            (analysis_json, match_id),
        )

    def get_match_ids(self, puuid: str) -> list[str]:
        """Get all stored match IDs for a summoner, newest first."""
        rows = self.fetch_all(
            "SELECT match_id FROM matches WHERE puuid = ? ORDER BY game_creation DESC",
            (puuid,),
        )
        return [r["match_id"] for r in rows]

    def get_match_count(self, puuid: str) -> int:
        """Count stored matches for a summoner."""
        row = self.fetch_one(
            "SELECT COUNT(*) as cnt FROM matches WHERE puuid = ?", (puuid,)
        )
        return row["cnt"] if row else 0

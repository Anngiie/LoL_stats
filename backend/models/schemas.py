"""
LoL Stats - Pydantic Schemas
=============================
Request/response models for the FastAPI backend.
Used for API validation and serialization.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ─── Summoner ──────────────────────────────────────────────

class SummonerResponse(BaseModel):
    puuid: str
    game_name: str
    tag_line: str
    region: str
    profile_icon_id: int = 0
    summoner_level: int = 0
    last_updated: str = ""
    is_tracked: bool = True
    match_count: int = 0


# ─── Matches ───────────────────────────────────────────────

class MatchSummary(BaseModel):
    """Compact match info for the match list view."""
    match_id: str
    champion_name: str
    champion_id: int
    win: bool
    kills: int
    deaths: int
    assists: int
    total_minions_killed: int
    vision_score: int
    gold_earned: int
    game_duration: int  # seconds
    game_creation: int  # epoch ms
    individual_position: Optional[str] = None
    queue_id: Optional[int] = None
    has_analysis: bool = False


class MatchDetail(BaseModel):
    """Full match data including all stats."""
    match_id: str
    puuid: str
    game_creation: int
    game_duration: int
    game_version: Optional[str] = None
    queue_id: Optional[int] = None
    platform_id: Optional[str] = None
    champion_id: int
    champion_name: str
    individual_position: Optional[str] = None
    team_id: Optional[int] = None
    win: bool
    kills: int
    deaths: int
    assists: int
    total_damage_dealt_to_champions: int
    total_damage_taken: int
    gold_earned: int
    total_minions_killed: int
    neutral_minions_killed: int
    vision_score: int
    vision_wards_bought: int
    wards_placed: int
    wards_killed: int
    control_wards_placed: int
    items: list[int] = Field(default_factory=lambda: [0] * 7)
    summoner1_id: int = 0
    summoner2_id: int = 0
    perk_primary_style: int = 0
    perk_sub_style: int = 0
    champ_level: int = 0
    double_kills: int = 0
    triple_kills: int = 0
    quadra_kills: int = 0
    penta_kills: int = 0
    turret_kills: int = 0
    inhibitor_kills: int = 0
    dragon_kills: int = 0
    baron_kills: int = 0
    analysis_data: Optional[dict] = None
    fetched_at: str = ""


class MatchListResponse(BaseModel):
    matches: list[MatchSummary]
    total: int
    page: int
    per_page: int
    has_more: bool


class RefreshResponse(BaseModel):
    puuid: str
    new_matches: int
    total_matches: int
    message: str


# ─── Analysis ──────────────────────────────────────────────

class AnalysisSection(BaseModel):
    status: str = "ok"  # "ok", "warning", "poor"
    score: Optional[int] = None  # 0-100, higher is better
    details: list[str] = Field(default_factory=list)
    benchmarks: Optional[dict] = None


class MatchAnalysisResponse(BaseModel):
    match_id: str
    champion_name: str
    position: str
    win: bool
    game_duration: int
    cs: AnalysisSection = Field(default_factory=AnalysisSection)
    kill_participation: AnalysisSection = Field(default_factory=AnalysisSection)
    vision: AnalysisSection = Field(default_factory=AnalysisSection)
    deaths: AnalysisSection = Field(default_factory=AnalysisSection)
    itemization: AnalysisSection = Field(default_factory=AnalysisSection)
    overall_grade: str = "N/A"  # S/A/B/C/D
    focus_areas: list[str] = Field(default_factory=list)
    summary: str = ""


class TrendsResponse(BaseModel):
    puuid: str
    matches_analyzed: int
    avg_kda: float = 0.0
    avg_cs_per_min: float = 0.0
    avg_vision_score: float = 0.0
    avg_kill_participation: float = 0.0
    win_rate: float = 0.0
    trend_direction: str = "stable"  # "improving", "stable", "declining"


# ─── Strategy ──────────────────────────────────────────────

class ChampionStrategy(BaseModel):
    """3-context champion strategy (vs enemy support / with jungler / with adc)."""
    vs_support: dict = Field(default_factory=dict)
    with_jungler: dict = Field(default_factory=dict)
    with_adc: dict = Field(default_factory=dict)
    personal_notes: str = ""
    overlay_priority: str = "normal"  # "high", "normal", "low"


class GlobalPreferences(BaseModel):
    overlay_auto_show_loading_screen: bool = True
    overlay_show_duration_seconds: int = 15
    overlay_opacity: float = 0.85
    overlay_font_size: int = 14
    overlay_font_family: str = "Segoe UI"
    overlay_width: int = 500
    overlay_x: int = 20
    overlay_y: int = 60


class StrategyData(BaseModel):
    version: int = 2
    last_updated: str = ""
    champions: dict[str, ChampionStrategy] = Field(default_factory=dict)
    global_preferences: GlobalPreferences = Field(default_factory=GlobalPreferences)


class StrategyUpdateRequest(BaseModel):
    """Partial update — any provided top-level key is applied."""
    vs_support: Optional[dict] = None
    with_jungler: Optional[dict] = None
    with_adc: Optional[dict] = None
    personal_notes: Optional[str] = None
    overlay_priority: Optional[str] = None


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    champions: list[str] = Field(default_factory=list)
    message: str = ""


# ─── Health ────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    riot_api_key_configured: bool = False
    database_ok: bool = False
    strategy_file_ok: bool = False
    live_client_reachable: bool = False
    version: str = "0.1.0"

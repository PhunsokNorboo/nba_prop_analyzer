"""
Data models/schemas for the NBA Prop Betting System.
Uses dataclasses for clean, typed data structures.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class PropType(Enum):
    """Supported prop types."""
    POINTS = "points"
    REBOUNDS = "rebounds"
    ASSISTS = "assists"
    THREES = "threes"
    PTS_REBS_ASTS = "pts_rebs_asts"
    PTS_ASTS = "pts_asts"
    PTS_REBS = "pts_rebs"
    REBS_ASTS = "rebs_asts"
    DOUBLE_DOUBLE = "double_double"


class EdgeType(Enum):
    """Types of betting edges."""
    INJURY = "injury"
    SCHEME = "scheme"
    PACE = "pace"
    ROLE = "role"
    SCHEDULE = "schedule"
    MATCHUP_HISTORY = "matchup_history"
    TEAM_EVOLUTION = "team_evolution"


class InjuryStatus(Enum):
    """Injury status classifications."""
    OUT = "out"
    DOUBTFUL = "doubtful"
    QUESTIONABLE = "questionable"
    PROBABLE = "probable"
    AVAILABLE = "available"
    DAY_TO_DAY = "day_to_day"


@dataclass
class Player:
    """Player information and basic stats."""
    id: int
    name: str
    team_id: int
    team_abbr: str
    position: str

    # Season averages
    ppg: float = 0.0
    rpg: float = 0.0
    apg: float = 0.0
    mpg: float = 0.0
    fg3m_pg: float = 0.0

    # Usage and role metrics
    usage_rate: float = 0.0

    # Recent form (last 5 games)
    recent_ppg: float = 0.0
    recent_rpg: float = 0.0
    recent_apg: float = 0.0
    recent_mpg: float = 0.0
    recent_fg3m: float = 0.0

    # Minutes stability
    minutes_std: float = 0.0
    is_starter: bool = False

    # Additional context
    games_played: int = 0
    injury_status: Optional[str] = None


@dataclass
class Team:
    """Team information and stats."""
    id: int
    abbr: str
    name: str

    # Pace and environment
    pace: float = 0.0
    offensive_rating: float = 0.0
    defensive_rating: float = 0.0

    # Points allowed by category
    opp_ppg: float = 0.0
    opp_rpg: float = 0.0
    opp_apg: float = 0.0
    opp_fg3m_pg: float = 0.0

    # Recent defensive form (last 5-10 games)
    recent_opp_ppg: float = 0.0
    recent_opp_rpg: float = 0.0
    recent_opp_apg: float = 0.0
    recent_opp_fg3m: float = 0.0

    # Defensive rankings (1 = best, 30 = worst)
    def_rank_pts: int = 15
    def_rank_reb: int = 15
    def_rank_ast: int = 15
    def_rank_fg3m: int = 15

    # Schedule context
    games_played: int = 0
    last_game_date: Optional[date] = None
    is_back_to_back: bool = False
    days_rest: int = 1


@dataclass
class Game:
    """A single NBA game."""
    id: str
    date: date
    home_team_id: int
    away_team_id: int
    home_team_abbr: str
    away_team_abbr: str

    # Vegas lines (if available)
    total: Optional[float] = None
    spread: Optional[float] = None
    home_ml: Optional[int] = None
    away_ml: Optional[int] = None

    # Game time
    start_time: Optional[datetime] = None

    # Status
    status: str = "scheduled"  # scheduled, in_progress, final


@dataclass
class Prop:
    """A player prop betting line."""
    player_id: int
    player_name: str
    team_abbr: str
    game_id: str
    opponent_abbr: str

    prop_type: str  # points, rebounds, etc.
    line: float
    over_odds: int  # American odds, e.g., -110
    under_odds: int

    book: str  # FanDuel, DraftKings

    # Metadata
    is_home: bool = True
    fetched_at: datetime = field(default_factory=datetime.now)

    def best_odds(self, direction: str = "over") -> int:
        """Get the better odds between books if we have multiple."""
        return self.over_odds if direction == "over" else self.under_odds


@dataclass
class Edge:
    """A discovered betting edge."""
    edge_type: str  # EdgeType value
    description: str  # Human-readable explanation
    affected_stats: List[str]  # ["rebounds", "points", etc.]
    strength: float  # 0.0 to 1.0

    # Supporting data for the edge
    supporting_data: Dict[str, Any] = field(default_factory=dict)

    # Which player(s) benefit
    benefiting_player_ids: List[int] = field(default_factory=list)

    # Context
    game_id: Optional[str] = None
    team_abbr: Optional[str] = None
    is_primary: bool = True  # Primary edge vs supporting/secondary


@dataclass
class Injury:
    """Player injury information."""
    player_id: int
    player_name: str
    team_id: int
    team_abbr: str
    status: str  # InjuryStatus value
    injury_type: str  # "knee", "ankle", etc.

    # Impact metrics
    usage_rate: float = 0.0  # How much usage this player has
    minutes_per_game: float = 0.0

    # Dates
    injury_date: Optional[date] = None
    expected_return: Optional[date] = None

    # Notes
    notes: str = ""


@dataclass
class PlayerGameLog:
    """Single game stats for a player."""
    player_id: int
    game_id: str
    game_date: date
    opponent_id: int
    opponent_abbr: str
    is_home: bool

    # Box score stats
    minutes: float
    points: int
    rebounds: int
    assists: int
    fg3m: int
    fgm: int
    fga: int
    ftm: int
    fta: int
    steals: int
    blocks: int
    turnovers: int

    # Did they start?
    started: bool = False

    # Result
    plus_minus: int = 0
    team_won: bool = False

    @property
    def pra(self) -> int:
        """Points + Rebounds + Assists."""
        return self.points + self.rebounds + self.assists

    @property
    def pts_asts(self) -> int:
        """Points + Assists."""
        return self.points + self.assists

    @property
    def pts_rebs(self) -> int:
        """Points + Rebounds."""
        return self.points + self.rebounds

    @property
    def rebs_asts(self) -> int:
        """Rebounds + Assists."""
        return self.rebounds + self.assists

    @property
    def has_double_double(self) -> bool:
        """Check for double-double."""
        stats = [self.points, self.rebounds, self.assists, self.steals, self.blocks]
        return sum(1 for s in stats if s >= 10) >= 2


@dataclass
class TeamDefenseStats:
    """Team defensive statistics by category."""
    team_id: int
    team_abbr: str

    # Season averages allowed
    pts_allowed: float
    reb_allowed: float
    ast_allowed: float
    fg3m_allowed: float

    # Rankings (1-30, lower is better defense)
    pts_rank: int
    reb_rank: int
    ast_rank: int
    fg3m_rank: int

    # Position-specific (if available)
    pts_to_guards: float = 0.0
    pts_to_forwards: float = 0.0
    pts_to_centers: float = 0.0
    reb_to_centers: float = 0.0

    # Recent form (last 5-10 games)
    recent_pts_allowed: float = 0.0
    recent_reb_allowed: float = 0.0
    recent_ast_allowed: float = 0.0
    recent_fg3m_allowed: float = 0.0

    # Sample info
    games_sampled: int = 0
    as_of_date: Optional[date] = None


@dataclass
class ScheduleContext:
    """Schedule and rest context for a team."""
    team_id: int
    team_abbr: str

    # Rest
    days_rest: int
    is_back_to_back: bool
    games_in_last_7_days: int

    # Travel
    is_home: bool
    travel_miles: float = 0.0
    timezone_changes: int = 0

    # Opponent context
    opponent_days_rest: int = 1
    opponent_is_b2b: bool = False

    # Advantage
    rest_advantage: int = 0  # Positive = we have more rest


@dataclass
class PropAnalysis:
    """Complete analysis for a single prop."""
    prop: Prop
    player: Player
    opponent: Team
    game: Game

    # Discovered edges
    edges: List[Edge] = field(default_factory=list)

    # Statistical context
    player_game_logs: List[PlayerGameLog] = field(default_factory=list)
    conditional_splits: Dict[str, Any] = field(default_factory=dict)

    # Schedule context
    schedule: Optional[ScheduleContext] = None

    # Projection
    projected_low: float = 0.0
    projected_high: float = 0.0
    projected_mid: float = 0.0

    # Direction (over/under)
    direction: str = "over"  # or "under"

    # Confidence scoring
    confidence_score: float = 0.0
    minutes_security_score: float = 0.0
    edge_strength_score: float = 0.0
    sample_quality_score: float = 0.0

    # Generated analysis
    narrative: str = ""
    risk_notes: List[str] = field(default_factory=list)

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.now)


@dataclass
class FormattedPick:
    """Final formatted pick for output."""
    player_name: str
    prop_type: str
    direction: str  # "Over" or "Under"
    line: float

    book: str
    odds: int

    projected_range: str  # "22.5 - 26.5"

    analysis: str  # 1-2 paragraph narrative
    risk_notes: str  # Brief risk summary

    # For ranking
    confidence_rank: int = 0

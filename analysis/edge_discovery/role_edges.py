"""
Role and usage-based edge discovery.
Identifies edges from role changes, usage shifts, and rotation adjustments.
"""
from typing import Dict, List, Optional
import statistics
import structlog

from config.settings import get_settings
from config.constants import EdgeType
from data.models.schemas import Edge, Game, Player, PlayerGameLog
from data.collectors.nba_stats import (
    get_player_game_logs, calculate_weighted_averages, enrich_player_with_stats
)

logger = structlog.get_logger()
settings = get_settings()


def find_role_edges(games: List[Game], players: Optional[List[Player]] = None) -> List[Edge]:
    """Discover edges from role changes and usage trends.

    Types of role edges:
    1. Recent usage increase
    2. Minutes trending up
    3. New starting role
    4. Elevated role due to teammate injury

    Args:
        games: Today's games
        players: Optional list of players to analyze

    Returns:
        List of role-based Edge objects
    """
    edges = []

    # If no players provided, this would need to fetch players for each team
    # For now, return empty if no players given
    if not players:
        logger.info("no_players_for_role_edges")
        return edges

    for player in players:
        player_edges = _analyze_player_role(player)
        edges.extend(player_edges)

    logger.info("found_role_edges", count=len(edges))
    return edges


def _analyze_player_role(player: Player) -> List[Edge]:
    """Analyze a single player's role for edges.

    Args:
        player: Player to analyze

    Returns:
        List of Edge objects for this player
    """
    edges = []

    # Get game logs
    logs = get_player_game_logs(player.id)
    if len(logs) < settings.min_minutes_last_n:
        return edges

    # Check for usage increase
    usage_edge = _check_usage_trend(player, logs)
    if usage_edge:
        edges.append(usage_edge)

    # Check for minutes increase
    minutes_edge = _check_minutes_trend(player, logs)
    if minutes_edge:
        edges.append(minutes_edge)

    # Check for new starter status
    starter_edge = _check_starter_change(player, logs)
    if starter_edge:
        edges.append(starter_edge)

    return edges


def _check_usage_trend(player: Player, logs: List[PlayerGameLog]) -> Optional[Edge]:
    """Check if player's usage is trending up.

    Args:
        player: Player info
        logs: Recent game logs

    Returns:
        Edge if usage is increasing, None otherwise
    """
    if len(logs) < 10:
        return None

    # Compare last 5 to previous 5
    recent_5 = logs[:5]
    previous_5 = logs[5:10]

    # Calculate average FGA as proxy for usage
    recent_fga = sum(g.fga for g in recent_5) / len(recent_5)
    previous_fga = sum(g.fga for g in previous_5) / len(previous_5)

    # Also check points
    recent_pts = sum(g.points for g in recent_5) / len(recent_5)
    previous_pts = sum(g.points for g in previous_5) / len(previous_5)

    # Significant increase: 20%+ FGA increase or 3+ points increase
    fga_increase = (recent_fga - previous_fga) / max(previous_fga, 1) * 100
    pts_increase = recent_pts - previous_pts

    if fga_increase >= 20 or pts_increase >= 3:
        strength = min(0.3 + (fga_increase / 100), 0.7)

        return Edge(
            edge_type=EdgeType.ROLE,
            description=f"{player.name}'s usage trending up: "
                       f"{previous_fga:.1f} → {recent_fga:.1f} FGA, "
                       f"{previous_pts:.1f} → {recent_pts:.1f} PPG",
            affected_stats=["points", "threes", "pts_rebs_asts", "pts_asts", "pts_rebs"],
            strength=strength,
            supporting_data={
                "player": player.name,
                "recent_fga": recent_fga,
                "previous_fga": previous_fga,
                "fga_increase_pct": fga_increase,
                "recent_pts": recent_pts,
                "previous_pts": previous_pts,
                "pts_increase": pts_increase,
                "edge_subtype": "usage_increase"
            },
            benefiting_player_ids=[player.id],
            team_abbr=player.team_abbr,
            is_primary=True
        )

    return None


def _check_minutes_trend(player: Player, logs: List[PlayerGameLog]) -> Optional[Edge]:
    """Check if player's minutes are trending up.

    Args:
        player: Player info
        logs: Recent game logs

    Returns:
        Edge if minutes increasing, None otherwise
    """
    if len(logs) < 10:
        return None

    recent_5 = logs[:5]
    previous_5 = logs[5:10]

    recent_mins = sum(g.minutes for g in recent_5) / len(recent_5)
    previous_mins = sum(g.minutes for g in previous_5) / len(previous_5)

    mins_increase = recent_mins - previous_mins

    # Significant: 3+ minute increase
    if mins_increase >= 3:
        strength = min(0.3 + (mins_increase / 10), 0.6)

        return Edge(
            edge_type=EdgeType.ROLE,
            description=f"{player.name}'s minutes trending up: "
                       f"{previous_mins:.1f} → {recent_mins:.1f} MPG (+{mins_increase:.1f})",
            affected_stats=["points", "rebounds", "assists", "threes",
                          "pts_rebs_asts", "pts_asts", "pts_rebs", "rebs_asts"],
            strength=strength,
            supporting_data={
                "player": player.name,
                "recent_mins": recent_mins,
                "previous_mins": previous_mins,
                "mins_increase": mins_increase,
                "edge_subtype": "minutes_increase"
            },
            benefiting_player_ids=[player.id],
            team_abbr=player.team_abbr,
            is_primary=True
        )

    return None


def _check_starter_change(player: Player, logs: List[PlayerGameLog]) -> Optional[Edge]:
    """Check if player recently became a starter.

    Args:
        player: Player info
        logs: Recent game logs

    Returns:
        Edge if newly starting, None otherwise
    """
    if len(logs) < 10:
        return None

    recent_5 = logs[:5]
    previous_5 = logs[5:10]

    recent_starts = sum(1 for g in recent_5 if g.started)
    previous_starts = sum(1 for g in previous_5 if g.started)

    # New starter: started 4+ of last 5 after starting 1 or fewer of previous 5
    if recent_starts >= 4 and previous_starts <= 1:
        return Edge(
            edge_type=EdgeType.ROLE,
            description=f"{player.name} has moved into starting lineup "
                       f"(started {recent_starts}/5 recent games vs {previous_starts}/5 before)",
            affected_stats=["points", "rebounds", "assists", "threes",
                          "pts_rebs_asts", "pts_asts", "pts_rebs", "rebs_asts"],
            strength=0.6,
            supporting_data={
                "player": player.name,
                "recent_starts": recent_starts,
                "previous_starts": previous_starts,
                "edge_subtype": "new_starter"
            },
            benefiting_player_ids=[player.id],
            team_abbr=player.team_abbr,
            is_primary=True
        )

    return None


def analyze_player_production_consistency(
    player: Player,
    prop_type: str,
    line: float
) -> Dict[str, float]:
    """Analyze how consistently a player hits a specific line.

    Args:
        player: Player to analyze
        prop_type: Type of prop (points, rebounds, etc.)
        line: The betting line

    Returns:
        Dict with hit rate, average, and consistency metrics
    """
    logs = get_player_game_logs(player.id)
    if not logs:
        return {}

    # Get the relevant stat from each game
    values = []
    for log in logs:
        if prop_type == "points":
            values.append(log.points)
        elif prop_type == "rebounds":
            values.append(log.rebounds)
        elif prop_type == "assists":
            values.append(log.assists)
        elif prop_type in ["threes", "fg3m"]:
            values.append(log.fg3m)
        elif prop_type in ["pra", "pts_rebs_asts"]:
            values.append(log.pra)
        elif prop_type == "pts_asts":
            values.append(log.pts_asts)
        elif prop_type == "pts_rebs":
            values.append(log.pts_rebs)
        elif prop_type == "rebs_asts":
            values.append(log.rebs_asts)

    if not values:
        return {}

    # Calculate metrics
    avg = sum(values) / len(values)
    over_count = sum(1 for v in values if v > line)
    hit_rate = over_count / len(values)

    # Standard deviation for consistency
    if len(values) > 1:
        std_dev = statistics.stdev(values)
    else:
        std_dev = 0.0

    # Recent hit rate (last 5)
    recent_values = values[:5]
    recent_hit_rate = sum(1 for v in recent_values if v > line) / len(recent_values) if recent_values else 0.0

    return {
        "season_avg": avg,
        "hit_rate": hit_rate,
        "over_count": over_count,
        "total_games": len(values),
        "std_dev": std_dev,
        "recent_hit_rate": recent_hit_rate,
        "recent_avg": sum(recent_values) / len(recent_values) if recent_values else 0.0
    }


def get_with_without_splits(
    player: Player,
    teammate_name: str
) -> Dict[str, Dict[str, float]]:
    """Calculate player's stats with and without a specific teammate.

    Args:
        player: Player to analyze
        teammate_name: Teammate to check

    Returns:
        Dict with 'with' and 'without' stat averages
    """
    # This would require lineup data which isn't directly available from basic APIs
    # Placeholder implementation
    return {
        "with": {},
        "without": {},
        "note": "Lineup data required for accurate with/without splits"
    }

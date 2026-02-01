"""
Player profiling module.
Analyzes how players generate their stats (shot profile, play types, etc.).
"""
from typing import Dict, List, Optional
import structlog

from data.models.schemas import Player, PlayerGameLog
from data.collectors.nba_stats import get_player_game_logs

logger = structlog.get_logger()


def build_player_profile(player: Player) -> Dict:
    """Build a comprehensive profile of how a player produces stats.

    Args:
        player: Player to profile

    Returns:
        Dict with profile information
    """
    logs = get_player_game_logs(player.id)

    if not logs:
        return {"error": "No game logs available"}

    profile = {
        "player_name": player.name,
        "team": player.team_abbr,
        "position": player.position,
        "games_analyzed": len(logs),
        "scoring_profile": _build_scoring_profile(logs),
        "rebounding_profile": _build_rebounding_profile(logs),
        "playmaking_profile": _build_playmaking_profile(logs),
        "minutes_profile": _build_minutes_profile(logs),
        "consistency": _calculate_consistency_metrics(logs)
    }

    return profile


def _build_scoring_profile(logs: List[PlayerGameLog]) -> Dict:
    """Analyze how player scores their points.

    Args:
        logs: Game logs

    Returns:
        Scoring profile dict
    """
    total_games = len(logs)
    if total_games == 0:
        return {}

    total_pts = sum(g.points for g in logs)
    total_fgm = sum(g.fgm for g in logs)
    total_fga = sum(g.fga for g in logs)
    total_fg3m = sum(g.fg3m for g in logs)
    total_ftm = sum(g.ftm for g in logs)
    total_fta = sum(g.fta for g in logs)

    # Calculate percentages
    fg_pct = (total_fgm / total_fga * 100) if total_fga > 0 else 0
    ft_pct = (total_ftm / total_fta * 100) if total_fta > 0 else 0

    # Point distribution
    pts_from_3 = total_fg3m * 3
    pts_from_2 = (total_fgm - total_fg3m) * 2
    pts_from_ft = total_ftm

    return {
        "ppg": total_pts / total_games,
        "fga_pg": total_fga / total_games,
        "fg_pct": fg_pct,
        "fg3m_pg": total_fg3m / total_games,
        "three_pt_rate": (total_fg3m / total_fga * 100) if total_fga > 0 else 0,
        "ftm_pg": total_ftm / total_games,
        "fta_pg": total_fta / total_games,
        "ft_pct": ft_pct,
        "pts_from_3_pct": (pts_from_3 / total_pts * 100) if total_pts > 0 else 0,
        "pts_from_2_pct": (pts_from_2 / total_pts * 100) if total_pts > 0 else 0,
        "pts_from_ft_pct": (pts_from_ft / total_pts * 100) if total_pts > 0 else 0,
        "scoring_style": _classify_scoring_style(logs)
    }


def _build_rebounding_profile(logs: List[PlayerGameLog]) -> Dict:
    """Analyze player's rebounding tendencies.

    Args:
        logs: Game logs

    Returns:
        Rebounding profile dict
    """
    total_games = len(logs)
    if total_games == 0:
        return {}

    total_reb = sum(g.rebounds for g in logs)

    return {
        "rpg": total_reb / total_games,
        "double_digit_reb_rate": sum(1 for g in logs if g.rebounds >= 10) / total_games,
        "rebound_floor": min(g.rebounds for g in logs) if logs else 0,
        "rebound_ceiling": max(g.rebounds for g in logs) if logs else 0,
    }


def _build_playmaking_profile(logs: List[PlayerGameLog]) -> Dict:
    """Analyze player's playmaking tendencies.

    Args:
        logs: Game logs

    Returns:
        Playmaking profile dict
    """
    total_games = len(logs)
    if total_games == 0:
        return {}

    total_ast = sum(g.assists for g in logs)
    total_tov = sum(g.turnovers for g in logs)

    ast_to_tov = total_ast / total_tov if total_tov > 0 else total_ast

    return {
        "apg": total_ast / total_games,
        "tov_pg": total_tov / total_games,
        "ast_to_tov_ratio": ast_to_tov,
        "double_digit_ast_rate": sum(1 for g in logs if g.assists >= 10) / total_games,
        "assist_floor": min(g.assists for g in logs) if logs else 0,
        "assist_ceiling": max(g.assists for g in logs) if logs else 0,
    }


def _build_minutes_profile(logs: List[PlayerGameLog]) -> Dict:
    """Analyze player's minutes patterns.

    Args:
        logs: Game logs

    Returns:
        Minutes profile dict
    """
    total_games = len(logs)
    if total_games == 0:
        return {}

    minutes_list = [g.minutes for g in logs]
    avg_minutes = sum(minutes_list) / total_games

    # Calculate variance
    if len(minutes_list) > 1:
        import statistics
        std_dev = statistics.stdev(minutes_list)
    else:
        std_dev = 0

    return {
        "mpg": avg_minutes,
        "minutes_std": std_dev,
        "minutes_floor": min(minutes_list),
        "minutes_ceiling": max(minutes_list),
        "started_rate": sum(1 for g in logs if g.started) / total_games,
        "30_plus_min_rate": sum(1 for g in logs if g.minutes >= 30) / total_games,
        "sub_20_min_rate": sum(1 for g in logs if g.minutes < 20) / total_games,
    }


def _calculate_consistency_metrics(logs: List[PlayerGameLog]) -> Dict:
    """Calculate consistency metrics across stat categories.

    Args:
        logs: Game logs

    Returns:
        Consistency metrics dict
    """
    if len(logs) < 5:
        return {}

    import statistics

    points = [g.points for g in logs]
    rebounds = [g.rebounds for g in logs]
    assists = [g.assists for g in logs]
    pra = [g.pra for g in logs]

    return {
        "points_std": statistics.stdev(points) if len(points) > 1 else 0,
        "rebounds_std": statistics.stdev(rebounds) if len(rebounds) > 1 else 0,
        "assists_std": statistics.stdev(assists) if len(assists) > 1 else 0,
        "pra_std": statistics.stdev(pra) if len(pra) > 1 else 0,
        "most_consistent_stat": _find_most_consistent_stat(logs),
        "most_volatile_stat": _find_most_volatile_stat(logs),
    }


def _classify_scoring_style(logs: List[PlayerGameLog]) -> str:
    """Classify player's scoring style.

    Args:
        logs: Game logs

    Returns:
        Scoring style description
    """
    total_fga = sum(g.fga for g in logs)
    total_fg3m = sum(g.fg3m for g in logs)
    total_fta = sum(g.fta for g in logs)
    total_fgm = sum(g.fgm for g in logs)

    if total_fga == 0:
        return "Unknown"

    three_rate = total_fg3m / total_fga
    ft_rate = total_fta / total_fga
    two_pt_rate = (total_fgm - total_fg3m) / total_fga

    # Classify based on shot distribution
    if three_rate > 0.4:
        return "Perimeter scorer (3PT heavy)"
    elif two_pt_rate > 0.5 and ft_rate > 0.3:
        return "Paint/rim finisher"
    elif ft_rate > 0.4:
        return "Foul drawer"
    elif three_rate > 0.25:
        return "Balanced scorer"
    else:
        return "Interior scorer"


def _find_most_consistent_stat(logs: List[PlayerGameLog]) -> str:
    """Find which stat category is most consistent for player."""
    import statistics

    if len(logs) < 3:
        return "Unknown"

    points = [g.points for g in logs]
    rebounds = [g.rebounds for g in logs]
    assists = [g.assists for g in logs]

    # Calculate coefficient of variation (std / mean) for comparison
    stats = {}

    for name, values in [("points", points), ("rebounds", rebounds), ("assists", assists)]:
        mean = sum(values) / len(values)
        if mean > 0:
            cv = statistics.stdev(values) / mean if len(values) > 1 else 0
            stats[name] = cv

    if not stats:
        return "Unknown"

    # Lower CV = more consistent
    return min(stats, key=stats.get)


def _find_most_volatile_stat(logs: List[PlayerGameLog]) -> str:
    """Find which stat category is most volatile for player."""
    import statistics

    if len(logs) < 3:
        return "Unknown"

    points = [g.points for g in logs]
    rebounds = [g.rebounds for g in logs]
    assists = [g.assists for g in logs]

    stats = {}

    for name, values in [("points", points), ("rebounds", rebounds), ("assists", assists)]:
        mean = sum(values) / len(values)
        if mean > 0:
            cv = statistics.stdev(values) / mean if len(values) > 1 else 0
            stats[name] = cv

    if not stats:
        return "Unknown"

    # Higher CV = more volatile
    return max(stats, key=stats.get)


def get_player_tendencies_vs_defense_type(
    player: Player,
    defense_weakness: str
) -> Dict:
    """Analyze how player performs vs specific defensive weaknesses.

    Args:
        player: Player to analyze
        defense_weakness: Type of defensive weakness (e.g., "poor_interior", "weak_perimeter")

    Returns:
        Analysis of player's fit vs this defense
    """
    profile = build_player_profile(player)

    fit_analysis = {
        "player": player.name,
        "defense_type": defense_weakness,
        "fit_score": 0.0,
        "reasoning": []
    }

    if defense_weakness == "poor_interior":
        # Check if player scores inside
        scoring = profile.get("scoring_profile", {})
        if scoring.get("pts_from_2_pct", 0) > 40:
            fit_analysis["fit_score"] += 0.3
            fit_analysis["reasoning"].append("Scores heavily inside")

        rebounding = profile.get("rebounding_profile", {})
        if rebounding.get("rpg", 0) > 5:
            fit_analysis["fit_score"] += 0.2
            fit_analysis["reasoning"].append("Strong rebounder")

    elif defense_weakness == "weak_perimeter":
        scoring = profile.get("scoring_profile", {})
        if scoring.get("fg3m_pg", 0) > 2:
            fit_analysis["fit_score"] += 0.4
            fit_analysis["reasoning"].append("Volume 3PT shooter")

        if scoring.get("three_pt_rate", 0) > 30:
            fit_analysis["fit_score"] += 0.2
            fit_analysis["reasoning"].append("High 3PT rate")

    elif defense_weakness == "poor_transition_d":
        scoring = profile.get("scoring_profile", {})
        if scoring.get("ppg", 0) > 15:
            fit_analysis["fit_score"] += 0.2
            fit_analysis["reasoning"].append("Volume scorer")

    return fit_analysis

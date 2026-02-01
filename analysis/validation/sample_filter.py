"""
Sample filtering for contextual splits.
Creates and applies filters to get relevant statistical samples.
"""
from typing import Callable, Dict, List, Optional
import structlog

from data.models.schemas import PlayerGameLog, PropAnalysis

logger = structlog.get_logger()


def filter_games_by_context(
    logs: List[PlayerGameLog],
    context: Dict
) -> List[PlayerGameLog]:
    """Filter game logs based on contextual criteria.

    Args:
        logs: All game logs
        context: Filter criteria dict

    Returns:
        Filtered game logs
    """
    filtered = logs

    # Filter by home/away
    if "is_home" in context:
        filtered = [g for g in filtered if g.is_home == context["is_home"]]

    # Filter by minimum minutes
    if "min_minutes" in context:
        filtered = [g for g in filtered if g.minutes >= context["min_minutes"]]

    # Filter by opponent
    if "opponent" in context:
        filtered = [g for g in filtered if g.opponent_abbr == context["opponent"]]

    # Filter by started
    if "started" in context:
        filtered = [g for g in filtered if g.started == context["started"]]

    # Filter by team result
    if "team_won" in context:
        filtered = [g for g in filtered if g.team_won == context["team_won"]]

    return filtered


def calculate_contextual_splits(
    analysis: PropAnalysis,
    min_sample: int = 3
) -> Dict[str, Dict]:
    """Calculate stats across various contextual splits.

    Args:
        analysis: The prop analysis
        min_sample: Minimum games required for a split

    Returns:
        Dict of split names to stat summaries
    """
    logs = analysis.player_game_logs
    prop_type = analysis.prop.prop_type
    splits = {}

    if not logs:
        return splits

    # Home vs Away
    home_games = [g for g in logs if g.is_home]
    away_games = [g for g in logs if not g.is_home]

    if len(home_games) >= min_sample:
        splits["home"] = _calculate_split_stats(home_games, prop_type)

    if len(away_games) >= min_sample:
        splits["away"] = _calculate_split_stats(away_games, prop_type)

    # As starter vs off bench
    starter_games = [g for g in logs if g.started]
    bench_games = [g for g in logs if not g.started]

    if len(starter_games) >= min_sample:
        splits["as_starter"] = _calculate_split_stats(starter_games, prop_type)

    if len(bench_games) >= min_sample:
        splits["off_bench"] = _calculate_split_stats(bench_games, prop_type)

    # High minutes games (26+)
    high_min_games = [g for g in logs if g.minutes >= 26]
    if len(high_min_games) >= min_sample:
        splits["26_plus_minutes"] = _calculate_split_stats(high_min_games, prop_type)

    # Vs specific opponent (if we have multiple games)
    opponent = analysis.opponent.abbr
    vs_opponent = [g for g in logs if g.opponent_abbr == opponent]
    if len(vs_opponent) >= 2:  # Lower threshold for H2H
        splits["vs_opponent"] = _calculate_split_stats(vs_opponent, prop_type)
        splits["vs_opponent"]["opponent"] = opponent

    # In wins vs losses
    wins = [g for g in logs if g.team_won]
    losses = [g for g in logs if not g.team_won]

    if len(wins) >= min_sample:
        splits["in_wins"] = _calculate_split_stats(wins, prop_type)

    if len(losses) >= min_sample:
        splits["in_losses"] = _calculate_split_stats(losses, prop_type)

    return splits


def _calculate_split_stats(logs: List[PlayerGameLog], prop_type: str) -> Dict:
    """Calculate stats for a specific split.

    Args:
        logs: Filtered game logs
        prop_type: Prop type to calculate

    Returns:
        Dict with stats
    """
    values = _get_values_for_prop(logs, prop_type)

    if not values:
        return {"games": 0}

    return {
        "games": len(logs),
        "avg": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
        "over_line_count": 0,  # Would need line to calculate
        "total": sum(values)
    }


def _get_values_for_prop(logs: List[PlayerGameLog], prop_type: str) -> List[float]:
    """Extract stat values based on prop type."""
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
        elif prop_type == "double_double":
            values.append(1 if log.has_double_double else 0)
    return values


def calculate_hit_rate(
    logs: List[PlayerGameLog],
    prop_type: str,
    line: float
) -> Dict:
    """Calculate how often player would have hit a specific line.

    Args:
        logs: Game logs
        prop_type: Type of prop
        line: The betting line

    Returns:
        Dict with hit rate stats
    """
    values = _get_values_for_prop(logs, prop_type)

    if not values:
        return {"hit_rate": 0.0, "games": 0}

    over_count = sum(1 for v in values if v > line)
    under_count = sum(1 for v in values if v < line)
    push_count = sum(1 for v in values if v == line)

    return {
        "games": len(values),
        "over_count": over_count,
        "under_count": under_count,
        "push_count": push_count,
        "over_rate": over_count / len(values),
        "under_rate": under_count / len(values),
        "avg": sum(values) / len(values),
        "line": line,
        "avg_vs_line": (sum(values) / len(values)) - line
    }


def find_best_contextual_angle(
    analysis: PropAnalysis,
    line: float
) -> Optional[Dict]:
    """Find the most favorable contextual split for this prop.

    Args:
        analysis: The prop analysis
        line: The betting line

    Returns:
        Best contextual angle or None
    """
    splits = calculate_contextual_splits(analysis)
    prop_type = analysis.prop.prop_type
    direction = analysis.direction

    best_split = None
    best_rate = 0.0

    for split_name, split_stats in splits.items():
        if split_stats.get("games", 0) < 3:
            continue

        # Get the relevant logs for this split
        logs = analysis.player_game_logs
        context = _split_name_to_context(split_name, analysis)
        filtered_logs = filter_games_by_context(logs, context)

        hit_stats = calculate_hit_rate(filtered_logs, prop_type, line)

        # Check hit rate based on direction
        rate = hit_stats["over_rate"] if direction == "over" else hit_stats["under_rate"]

        if rate > best_rate and rate >= 0.6:  # At least 60% hit rate
            best_rate = rate
            best_split = {
                "name": split_name,
                "hit_rate": rate,
                "games": hit_stats["games"],
                "avg": hit_stats["avg"],
                "description": _describe_split(split_name, hit_stats, direction)
            }

    return best_split


def _split_name_to_context(split_name: str, analysis: PropAnalysis) -> Dict:
    """Convert split name to filter context."""
    context = {}

    if split_name == "home":
        context["is_home"] = True
    elif split_name == "away":
        context["is_home"] = False
    elif split_name == "as_starter":
        context["started"] = True
    elif split_name == "off_bench":
        context["started"] = False
    elif split_name == "26_plus_minutes":
        context["min_minutes"] = 26
    elif split_name == "vs_opponent":
        context["opponent"] = analysis.opponent.abbr
    elif split_name == "in_wins":
        context["team_won"] = True
    elif split_name == "in_losses":
        context["team_won"] = False

    return context


def _describe_split(split_name: str, stats: Dict, direction: str) -> str:
    """Generate human-readable description of a split."""
    rate = stats["over_rate"] if direction == "over" else stats["under_rate"]
    pct = rate * 100

    descriptions = {
        "home": f"At home: {direction} in {stats['over_count'] if direction == 'over' else stats['under_count']}/{stats['games']} games ({pct:.0f}%)",
        "away": f"On the road: {direction} in {stats['over_count'] if direction == 'over' else stats['under_count']}/{stats['games']} games ({pct:.0f}%)",
        "as_starter": f"As starter: {direction} in {stats['over_count'] if direction == 'over' else stats['under_count']}/{stats['games']} games ({pct:.0f}%)",
        "26_plus_minutes": f"With 26+ minutes: {direction} in {stats['over_count'] if direction == 'over' else stats['under_count']}/{stats['games']} games ({pct:.0f}%)",
        "vs_opponent": f"vs this opponent: {direction} in {stats['over_count'] if direction == 'over' else stats['under_count']}/{stats['games']} games ({pct:.0f}%)",
    }

    return descriptions.get(split_name, f"{split_name}: {pct:.0f}% {direction} rate")

"""
Narrative builder that structures data for Claude API calls.
Prepares all context needed to generate analysis.
"""
from typing import Dict, List, Optional
import structlog

from data.models.schemas import PropAnalysis, Edge
from analysis.validation.sample_filter import calculate_contextual_splits
from analysis.profiles.team_defense import build_team_defense_profile
from generation.prompts import format_analysis_prompt

logger = structlog.get_logger()


def build_analysis_context(analysis: PropAnalysis) -> Dict:
    """Build complete context for Claude analysis generation.

    Args:
        analysis: The prop analysis with all data

    Returns:
        Dict with all context needed for prompt
    """
    context = {
        "player": _build_player_context(analysis),
        "prop": _build_prop_context(analysis),
        "game": _build_game_context(analysis),
        "edges": _build_edges_context(analysis),
        "stats": _build_stats_context(analysis),
        "opponent": _build_opponent_context(analysis),
        "splits": _build_splits_context(analysis),
        "schedule": _build_schedule_context(analysis),
        "projection": {
            "low": analysis.projected_low,
            "high": analysis.projected_high,
            "mid": analysis.projected_mid
        }
    }

    return context


def _build_player_context(analysis: PropAnalysis) -> Dict:
    """Build player context."""
    player = analysis.player
    return {
        "name": player.name,
        "team_abbr": player.team_abbr,
        "position": player.position or "Unknown",
        "ppg": player.ppg,
        "rpg": player.rpg,
        "apg": player.apg,
        "mpg": player.mpg,
        "fg3m_pg": player.fg3m_pg,
        "is_starter": player.is_starter,
        "games_played": player.games_played
    }


def _build_prop_context(analysis: PropAnalysis) -> Dict:
    """Build prop context."""
    prop = analysis.prop
    return {
        "type": prop.prop_type,
        "line": prop.line,
        "direction": analysis.direction,
        "over_odds": prop.over_odds,
        "under_odds": prop.under_odds,
        "book": prop.book,
        "best_odds": prop.over_odds if analysis.direction == "over" else prop.under_odds
    }


def _build_game_context(analysis: PropAnalysis) -> Dict:
    """Build game context."""
    game = analysis.game
    prop = analysis.prop

    is_home = prop.is_home
    home_away = "vs" if is_home else "@"

    return {
        "game_id": game.id,
        "opponent_abbr": analysis.opponent.abbr,
        "is_home": is_home,
        "home_away": home_away,
        "total": game.total,
        "spread": game.spread
    }


def _build_edges_context(analysis: PropAnalysis) -> List[Dict]:
    """Build edges context."""
    edges_data = []
    for edge in analysis.edges:
        edges_data.append({
            "edge_type": edge.edge_type,
            "description": edge.description,
            "affected_stats": edge.affected_stats,
            "strength": edge.strength,
            "supporting_data": edge.supporting_data,
            "is_primary": edge.is_primary
        })
    return edges_data


def _build_stats_context(analysis: PropAnalysis) -> Dict:
    """Build statistical context from game logs."""
    logs = analysis.player_game_logs
    prop_type = analysis.prop.prop_type

    if not logs:
        return {
            "season": {},
            "recent_5": {},
            "recent_10": {}
        }

    # Season stats
    season_stats = _calculate_averages(logs, prop_type)

    # Last 5 games
    recent_5 = _calculate_averages(logs[:5], prop_type) if len(logs) >= 5 else season_stats

    # Last 10 games
    recent_10 = _calculate_averages(logs[:10], prop_type) if len(logs) >= 10 else season_stats

    return {
        "season": season_stats,
        "recent_5": recent_5,
        "recent_10": recent_10,
        "games_played": len(logs)
    }


def _calculate_averages(logs: List, prop_type: str) -> Dict:
    """Calculate stat averages from game logs."""
    if not logs:
        return {}

    n = len(logs)
    return {
        "ppg": sum(g.points for g in logs) / n,
        "rpg": sum(g.rebounds for g in logs) / n,
        "apg": sum(g.assists for g in logs) / n,
        "fg3m_pg": sum(g.fg3m for g in logs) / n,
        "mpg": sum(g.minutes for g in logs) / n,
        "pra": sum(g.pra for g in logs) / n,
        "games": n
    }


def _build_opponent_context(analysis: PropAnalysis) -> Dict:
    """Build opponent defensive context."""
    opponent = analysis.opponent

    defense_profile = build_team_defense_profile(opponent.abbr)

    return {
        "abbr": opponent.abbr,
        "name": opponent.name,
        "pts_allowed": opponent.opp_ppg,
        "reb_allowed": opponent.opp_rpg,
        "ast_allowed": opponent.opp_apg,
        "pts_rank": opponent.def_rank_pts,
        "reb_rank": opponent.def_rank_reb,
        "ast_rank": opponent.def_rank_ast,
        "weaknesses": defense_profile.get("weaknesses", []),
        "strengths": defense_profile.get("strengths", []),
        "scheme": defense_profile.get("scheme_indicators", {})
    }


def _build_splits_context(analysis: PropAnalysis) -> Dict:
    """Build contextual splits."""
    splits = calculate_contextual_splits(analysis)
    return splits


def _build_schedule_context(analysis: PropAnalysis) -> Dict:
    """Build schedule context."""
    schedule = analysis.schedule
    if not schedule:
        return {}

    return {
        "days_rest": schedule.days_rest,
        "is_b2b": schedule.is_back_to_back,
        "is_home": schedule.is_home,
        "rest_advantage": schedule.rest_advantage,
        "opponent_b2b": schedule.opponent_is_b2b,
        "games_in_7_days": schedule.games_in_last_7_days
    }


def format_schedule_text(context: Dict) -> str:
    """Format schedule context as text for prompt."""
    if not context:
        return ""

    parts = []

    if context.get("is_b2b"):
        parts.append("Playing on back-to-back")

    if context.get("opponent_b2b"):
        parts.append("Opponent on B2B")

    rest_adv = context.get("rest_advantage", 0)
    if rest_adv > 0:
        parts.append(f"{rest_adv} days more rest than opponent")
    elif rest_adv < 0:
        parts.append(f"{abs(rest_adv)} days less rest than opponent")

    return ". ".join(parts) if parts else "Normal schedule"


def build_claude_prompt(analysis: PropAnalysis) -> str:
    """Build the complete prompt for Claude API.

    Args:
        analysis: The prop analysis

    Returns:
        Formatted prompt string
    """
    context = build_analysis_context(analysis)

    schedule_text = format_schedule_text(context.get("schedule", {}))

    # Format H2H history
    h2h = analysis.conditional_splits.get("vs_opponent", {})

    prompt = format_analysis_prompt(
        player_name=context["player"]["name"],
        team_abbr=context["player"]["team_abbr"],
        position=context["player"]["position"],
        prop_type=context["prop"]["type"],
        direction=context["prop"]["direction"],
        line=context["prop"]["line"],
        odds=context["prop"]["best_odds"],
        book=context["prop"]["book"],
        opponent_abbr=context["opponent"]["abbr"],
        home_away=context["game"]["home_away"],
        edges=analysis.edges,
        season_stats=context["stats"]["season"],
        recent_stats=context["stats"]["recent_5"],
        medium_stats=context["stats"]["recent_10"],
        opponent_defense=context["opponent"],
        contextual_splits=context["splits"],
        h2h_history=h2h,
        projected_low=context["projection"]["low"],
        projected_high=context["projection"]["high"],
        schedule_context=schedule_text
    )

    return prompt

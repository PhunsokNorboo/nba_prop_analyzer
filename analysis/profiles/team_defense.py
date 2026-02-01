"""
Team defensive profiling module.
Analyzes team defensive tendencies and weaknesses.
"""
from typing import Dict, List, Optional
import structlog

from config.constants import TEAM_IDS, TEAM_ID_TO_ABBR
from data.models.schemas import Team, TeamDefenseStats
from data.collectors.nba_stats import get_team_stats, get_team_defensive_stats

logger = structlog.get_logger()


def build_team_defense_profile(team_abbr: str) -> Dict:
    """Build a comprehensive defensive profile for a team.

    Args:
        team_abbr: Team abbreviation

    Returns:
        Defensive profile dict
    """
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return {"error": f"Unknown team: {team_abbr}"}

    defense_stats = get_team_defensive_stats(team_id)

    if not defense_stats:
        return {"error": "Could not fetch defensive stats"}

    # Get league rankings context
    all_teams_df = get_team_stats()

    profile = {
        "team": team_abbr,
        "overall_defense": _build_overall_defense(defense_stats),
        "weaknesses": _identify_weaknesses(defense_stats),
        "strengths": _identify_strengths(defense_stats),
        "stat_allowed_ranks": {
            "points": defense_stats.pts_rank,
            "rebounds": defense_stats.reb_rank,
            "assists": defense_stats.ast_rank,
            "threes": defense_stats.fg3m_rank,
        },
        "stats_allowed": {
            "ppg": defense_stats.pts_allowed,
            "rpg": defense_stats.reb_allowed,
            "apg": defense_stats.ast_allowed,
            "fg3m_pg": defense_stats.fg3m_allowed,
        },
        "recent_form": _get_recent_defensive_form(team_id),
        "scheme_indicators": _infer_defensive_scheme(defense_stats)
    }

    return profile


def _build_overall_defense(stats: TeamDefenseStats) -> Dict:
    """Summarize overall defensive quality.

    Args:
        stats: Team defensive stats

    Returns:
        Overall defense summary
    """
    # Average rank across categories
    avg_rank = (stats.pts_rank + stats.reb_rank + stats.ast_rank + stats.fg3m_rank) / 4

    if avg_rank <= 10:
        tier = "Elite"
    elif avg_rank <= 15:
        tier = "Above Average"
    elif avg_rank <= 20:
        tier = "Average"
    elif avg_rank <= 25:
        tier = "Below Average"
    else:
        tier = "Poor"

    return {
        "tier": tier,
        "avg_rank": avg_rank,
        "games_sampled": stats.games_sampled
    }


def _identify_weaknesses(stats: TeamDefenseStats) -> List[Dict]:
    """Identify defensive weaknesses (bottom 10 in any category).

    Args:
        stats: Team defensive stats

    Returns:
        List of weakness dicts
    """
    weaknesses = []

    if stats.pts_rank >= 21:
        weaknesses.append({
            "category": "points",
            "rank": stats.pts_rank,
            "allowed": stats.pts_allowed,
            "severity": "major" if stats.pts_rank >= 26 else "moderate",
            "description": f"Allows {stats.pts_allowed:.1f} PPG (#{stats.pts_rank} in NBA)"
        })

    if stats.reb_rank >= 21:
        weaknesses.append({
            "category": "rebounds",
            "rank": stats.reb_rank,
            "allowed": stats.reb_allowed,
            "severity": "major" if stats.reb_rank >= 26 else "moderate",
            "description": f"Allows {stats.reb_allowed:.1f} RPG (#{stats.reb_rank} in NBA)"
        })

    if stats.ast_rank >= 21:
        weaknesses.append({
            "category": "assists",
            "rank": stats.ast_rank,
            "allowed": stats.ast_allowed,
            "severity": "major" if stats.ast_rank >= 26 else "moderate",
            "description": f"Allows {stats.ast_allowed:.1f} APG (#{stats.ast_rank} in NBA)"
        })

    if stats.fg3m_rank >= 21:
        weaknesses.append({
            "category": "threes",
            "rank": stats.fg3m_rank,
            "allowed": stats.fg3m_allowed,
            "severity": "major" if stats.fg3m_rank >= 26 else "moderate",
            "description": f"Allows {stats.fg3m_allowed:.1f} 3PM/G (#{stats.fg3m_rank} in NBA)"
        })

    return weaknesses


def _identify_strengths(stats: TeamDefenseStats) -> List[Dict]:
    """Identify defensive strengths (top 10 in any category).

    Args:
        stats: Team defensive stats

    Returns:
        List of strength dicts
    """
    strengths = []

    if stats.pts_rank <= 10:
        strengths.append({
            "category": "points",
            "rank": stats.pts_rank,
            "description": f"Elite scoring defense (#{stats.pts_rank})"
        })

    if stats.reb_rank <= 10:
        strengths.append({
            "category": "rebounds",
            "rank": stats.reb_rank,
            "description": f"Strong rebounding defense (#{stats.reb_rank})"
        })

    if stats.ast_rank <= 10:
        strengths.append({
            "category": "assists",
            "rank": stats.ast_rank,
            "description": f"Limits playmaking (#{stats.ast_rank})"
        })

    if stats.fg3m_rank <= 10:
        strengths.append({
            "category": "threes",
            "rank": stats.fg3m_rank,
            "description": f"Strong perimeter defense (#{stats.fg3m_rank})"
        })

    return strengths


def _get_recent_defensive_form(team_id: int, last_n: int = 5) -> Dict:
    """Get team's recent defensive performance.

    Args:
        team_id: NBA team ID
        last_n: Number of games

    Returns:
        Recent form dict
    """
    recent_stats = get_team_defensive_stats(team_id, last_n_games=last_n)

    if not recent_stats:
        return {}

    return {
        "games": last_n,
        "recent_pts_allowed": recent_stats.recent_pts_allowed,
        "recent_reb_allowed": recent_stats.recent_reb_allowed,
        "recent_ast_allowed": recent_stats.recent_ast_allowed,
        "recent_fg3m_allowed": recent_stats.recent_fg3m_allowed,
    }


def _infer_defensive_scheme(stats: TeamDefenseStats) -> Dict:
    """Infer defensive scheme tendencies from stats.

    This is approximate - real scheme analysis would need play-by-play data.

    Args:
        stats: Team defensive stats

    Returns:
        Scheme indicators dict
    """
    indicators = {}

    # High 3PM allowed with low paint points = switching/perimeter focus
    # Low 3PM allowed with high paint points = drop coverage
    # This is very simplified

    if stats.fg3m_rank >= 21 and stats.pts_rank <= 15:
        indicators["likely_scheme"] = "Drop coverage / pack the paint"
        indicators["vulnerable_to"] = "3PT shooters"
    elif stats.fg3m_rank <= 10 and stats.pts_rank >= 21:
        indicators["likely_scheme"] = "Aggressive perimeter / switching"
        indicators["vulnerable_to"] = "Rim attacks, paint scorers"
    else:
        indicators["likely_scheme"] = "Mixed/standard"
        indicators["vulnerable_to"] = "Balanced attacks"

    return indicators


def compare_offense_to_defense(
    offensive_team: str,
    defensive_team: str
) -> Dict:
    """Compare how an offense matches up against a specific defense.

    Args:
        offensive_team: Team on offense
        defensive_team: Team on defense

    Returns:
        Matchup comparison dict
    """
    defense_profile = build_team_defense_profile(defensive_team)

    if "error" in defense_profile:
        return defense_profile

    # Get offensive team's tendencies (would need more data)
    # For now, return defensive weakness analysis

    matchup = {
        "offense": offensive_team,
        "defense": defensive_team,
        "defensive_weaknesses": defense_profile.get("weaknesses", []),
        "defensive_strengths": defense_profile.get("strengths", []),
        "recommended_attack_areas": [],
        "areas_to_avoid": []
    }

    # Map weaknesses to attack recommendations
    for weakness in defense_profile.get("weaknesses", []):
        cat = weakness["category"]
        if cat == "points":
            matchup["recommended_attack_areas"].append("Scoring in general")
        elif cat == "rebounds":
            matchup["recommended_attack_areas"].append("Offensive rebounding, second chances")
        elif cat == "assists":
            matchup["recommended_attack_areas"].append("Ball movement, playmaking")
        elif cat == "threes":
            matchup["recommended_attack_areas"].append("Perimeter shooting")

    # Map strengths to areas to avoid
    for strength in defense_profile.get("strengths", []):
        cat = strength["category"]
        if cat == "threes":
            matchup["areas_to_avoid"].append("Contested 3s, low-percentage perimeter shots")
        elif cat == "rebounds":
            matchup["areas_to_avoid"].append("Relying on second chances")

    return matchup


def get_worst_defensive_teams(stat_category: str, top_n: int = 10) -> List[str]:
    """Get teams with worst defense in a specific category.

    Args:
        stat_category: "points", "rebounds", "assists", or "threes"
        top_n: Number of teams to return

    Returns:
        List of team abbreviations (worst first)
    """
    worst_teams = []

    for abbr, team_id in TEAM_IDS.items():
        stats = get_team_defensive_stats(team_id)
        if not stats:
            continue

        if stat_category == "points":
            rank = stats.pts_rank
        elif stat_category == "rebounds":
            rank = stats.reb_rank
        elif stat_category == "assists":
            rank = stats.ast_rank
        elif stat_category == "threes":
            rank = stats.fg3m_rank
        else:
            continue

        worst_teams.append((abbr, rank))

    # Sort by rank descending (higher rank = worse defense)
    worst_teams.sort(key=lambda x: x[1], reverse=True)

    return [team[0] for team in worst_teams[:top_n]]

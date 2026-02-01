"""
Injury-based edge discovery.
Identifies betting opportunities created by player injuries.
"""
from datetime import date
from typing import Dict, List, Optional
import structlog

from config.settings import get_settings
from config.constants import STAT_TO_PROP_MAP, EdgeType
from data.models.schemas import Edge, Game, Injury, Player
from data.collectors.injury_tracker import get_injury_report, get_team_injuries
from data.collectors.nba_stats import get_player_game_logs, enrich_player_with_stats

logger = structlog.get_logger()
settings = get_settings()


def find_injury_edges(games: List[Game]) -> List[Edge]:
    """Discover edges created by injuries across today's slate.

    Types of injury edges:
    1. Teammate out → increased usage/stats for remaining players
    2. Opponent key player out → easier matchup for opposing players
    3. Defender out → scoring opportunity for matchup

    Args:
        games: Today's games

    Returns:
        List of injury-based Edge objects
    """
    edges = []
    injury_report = get_injury_report()

    for game in games:
        # Check home team injuries for away team opportunities
        home_injuries = injury_report.get(game.home_team_abbr, [])
        away_injuries = injury_report.get(game.away_team_abbr, [])

        # Opponent key player out → opportunity for other team
        edges.extend(_find_opponent_injury_edges(
            injured_team=game.home_team_abbr,
            injuries=home_injuries,
            benefiting_team=game.away_team_abbr,
            game=game
        ))
        edges.extend(_find_opponent_injury_edges(
            injured_team=game.away_team_abbr,
            injuries=away_injuries,
            benefiting_team=game.home_team_abbr,
            game=game
        ))

        # Teammate out → increased role for remaining players
        edges.extend(_find_teammate_out_edges(
            team_abbr=game.home_team_abbr,
            injuries=home_injuries,
            game=game
        ))
        edges.extend(_find_teammate_out_edges(
            team_abbr=game.away_team_abbr,
            injuries=away_injuries,
            game=game
        ))

    logger.info("found_injury_edges", count=len(edges))
    return edges


def _find_opponent_injury_edges(
    injured_team: str,
    injuries: List[Injury],
    benefiting_team: str,
    game: Game
) -> List[Edge]:
    """Find edges where opponent's injury benefits our players.

    Args:
        injured_team: Team with injuries
        injuries: List of injuries
        benefiting_team: Team that benefits
        game: Game context

    Returns:
        List of Edge objects
    """
    edges = []

    for injury in injuries:
        if injury.status not in ["out", "doubtful"]:
            continue

        # Determine what stats are affected by this player being out
        affected_stats = _get_affected_stats_from_injury(injury)
        if not affected_stats:
            continue

        # Calculate edge strength based on player importance
        strength = _calculate_injury_edge_strength(injury)
        if strength < settings.min_edge_strength:
            continue

        edge = Edge(
            edge_type=EdgeType.INJURY,
            description=f"{injury.player_name} ({injured_team}) is {injury.status} - "
                       f"{benefiting_team} players benefit",
            affected_stats=affected_stats,
            strength=strength,
            supporting_data={
                "injured_player": injury.player_name,
                "injured_team": injured_team,
                "injury_type": injury.injury_type,
                "injury_status": injury.status,
                "benefiting_team": benefiting_team,
                "usage_lost": injury.usage_rate,
                "minutes_lost": injury.minutes_per_game
            },
            game_id=game.id,
            team_abbr=benefiting_team,
            is_primary=True
        )
        edges.append(edge)

    return edges


def _find_teammate_out_edges(
    team_abbr: str,
    injuries: List[Injury],
    game: Game
) -> List[Edge]:
    """Find edges where teammate injury creates opportunity.

    Args:
        team_abbr: Team with injuries
        injuries: List of injuries
        game: Game context

    Returns:
        List of Edge objects
    """
    edges = []

    for injury in injuries:
        if injury.status not in ["out", "doubtful"]:
            continue

        # High usage players create opportunities when out
        if injury.usage_rate < 15.0 and injury.minutes_per_game < 25.0:
            continue

        affected_stats = _get_affected_stats_from_injury(injury)
        strength = _calculate_teammate_out_strength(injury)

        if strength < settings.min_edge_strength:
            continue

        edge = Edge(
            edge_type=EdgeType.INJURY,
            description=f"With {injury.player_name} out, {team_abbr} teammates get increased opportunity",
            affected_stats=affected_stats,
            strength=strength,
            supporting_data={
                "injured_player": injury.player_name,
                "team": team_abbr,
                "usage_available": injury.usage_rate,
                "minutes_available": injury.minutes_per_game,
                "edge_subtype": "teammate_out"
            },
            game_id=game.id,
            team_abbr=team_abbr,
            is_primary=True
        )
        edges.append(edge)

    return edges


def _get_affected_stats_from_injury(injury: Injury) -> List[str]:
    """Determine which stats are affected based on injured player's role.

    Args:
        injury: Injury information

    Returns:
        List of affected stat types
    """
    # This would ideally look at the player's actual production profile
    # For now, we make educated guesses based on position and role

    affected = []

    # If it's a high-usage player, affects points
    if injury.usage_rate >= 20.0:
        affected.extend(["points", "pts_rebs_asts", "pts_asts"])

    # If it's a big man, affects rebounds
    injury_notes = (injury.notes or "").lower()
    player_name = injury.player_name.lower()

    # Big man indicators (would be better with position data)
    big_man_keywords = ["center", "forward", "big", "rim", "paint"]
    if any(kw in injury_notes for kw in big_man_keywords):
        affected.extend(["rebounds", "pts_rebs_asts", "pts_rebs", "rebs_asts"])

    # Playmaker indicators
    playmaker_keywords = ["guard", "point", "playmaker", "ball-handler"]
    if any(kw in injury_notes for kw in playmaker_keywords):
        affected.extend(["assists", "pts_rebs_asts", "pts_asts", "rebs_asts"])

    # Default: assume affects points if we have no other info
    if not affected and injury.usage_rate >= 15.0:
        affected = ["points", "pts_rebs_asts"]

    return list(set(affected))


def _calculate_injury_edge_strength(injury: Injury) -> float:
    """Calculate edge strength based on injury significance.

    Args:
        injury: Injury information

    Returns:
        Edge strength from 0.0 to 1.0
    """
    base_strength = 0.3

    # Higher usage = bigger edge
    if injury.usage_rate >= 30.0:
        base_strength += 0.3
    elif injury.usage_rate >= 25.0:
        base_strength += 0.2
    elif injury.usage_rate >= 20.0:
        base_strength += 0.1

    # More minutes = bigger edge
    if injury.minutes_per_game >= 35.0:
        base_strength += 0.2
    elif injury.minutes_per_game >= 30.0:
        base_strength += 0.1

    # Confirmed OUT is stronger than doubtful
    if injury.status == "out":
        base_strength += 0.1

    return min(base_strength, 1.0)


def _calculate_teammate_out_strength(injury: Injury) -> float:
    """Calculate edge strength for teammate out scenario.

    Args:
        injury: Injury information

    Returns:
        Edge strength from 0.0 to 1.0
    """
    # Teammate edges are generally weaker than opponent edges
    # because usage redistribution is uncertain
    base_strength = 0.2

    if injury.usage_rate >= 30.0:
        base_strength += 0.25
    elif injury.usage_rate >= 25.0:
        base_strength += 0.15
    elif injury.usage_rate >= 20.0:
        base_strength += 0.1

    if injury.minutes_per_game >= 35.0:
        base_strength += 0.15
    elif injury.minutes_per_game >= 30.0:
        base_strength += 0.1

    return min(base_strength, 0.8)


def get_players_benefiting_from_injuries(
    injuries: List[Injury],
    team_abbr: str
) -> List[dict]:
    """Identify specific players who benefit from injuries.

    Args:
        injuries: List of current injuries
        team_abbr: Team to check (same team or opponent)

    Returns:
        List of dicts with player info and expected benefit
    """
    beneficiaries = []

    # This would ideally pull actual roster and player data
    # For now, returns placeholder structure
    for injury in injuries:
        if injury.status not in ["out", "doubtful"]:
            continue

        beneficiaries.append({
            "injured_player": injury.player_name,
            "usage_available": injury.usage_rate,
            "minutes_available": injury.minutes_per_game,
            "affected_stats": _get_affected_stats_from_injury(injury)
        })

    return beneficiaries

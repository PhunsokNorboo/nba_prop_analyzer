"""
Scheme and matchup-based edge discovery.
Identifies edges from defensive coverages, play styles, and tactical mismatches.
"""
from typing import Dict, List, Optional
import structlog

from config.settings import get_settings
from config.constants import EdgeType
from data.models.schemas import Edge, Game, Team, Player, TeamDefenseStats
from data.collectors.nba_stats import get_team_defensive_stats, get_team_stats

logger = structlog.get_logger()
settings = get_settings()


def find_scheme_edges(games: List[Game]) -> List[Edge]:
    """Discover edges from defensive schemes and matchups.

    Types of scheme edges:
    1. Poor defense vs specific stat type (e.g., bad rebounding team)
    2. Pace mismatch (fast vs slow teams)
    3. Scheme tendencies (drop coverage, trapping, switching)

    Args:
        games: Today's games

    Returns:
        List of scheme-based Edge objects
    """
    edges = []

    for game in games:
        # Get defensive stats for both teams
        home_defense = get_team_defensive_stats(game.home_team_id)
        away_defense = get_team_defensive_stats(game.away_team_id)

        if not home_defense or not away_defense:
            continue

        # Find edges for away team (vs home defense)
        edges.extend(_find_defensive_weakness_edges(
            defense=home_defense,
            attacking_team=game.away_team_abbr,
            defending_team=game.home_team_abbr,
            game=game
        ))

        # Find edges for home team (vs away defense)
        edges.extend(_find_defensive_weakness_edges(
            defense=away_defense,
            attacking_team=game.home_team_abbr,
            defending_team=game.away_team_abbr,
            game=game
        ))

    logger.info("found_scheme_edges", count=len(edges))
    return edges


def _find_defensive_weakness_edges(
    defense: TeamDefenseStats,
    attacking_team: str,
    defending_team: str,
    game: Game
) -> List[Edge]:
    """Find edges from defensive weaknesses.

    Args:
        defense: Defending team's defensive stats
        attacking_team: Team on offense
        defending_team: Team on defense
        game: Game context

    Returns:
        List of Edge objects
    """
    edges = []

    # Bottom half in points allowed (rank 16-30) - relaxed for more coverage
    if defense.pts_rank >= 16:
        strength = 0.4 + ((defense.pts_rank - 20) * 0.03)
        edges.append(Edge(
            edge_type=EdgeType.SCHEME,
            description=f"{defending_team} ranks {defense.pts_rank}th in points allowed "
                       f"({defense.pts_allowed:.1f} PPG) - scoring opportunity for {attacking_team}",
            affected_stats=["points", "pts_rebs_asts", "pts_asts", "pts_rebs"],
            strength=min(strength, 0.8),
            supporting_data={
                "defensive_stat": "points",
                "rank": defense.pts_rank,
                "allowed": defense.pts_allowed,
                "defending_team": defending_team,
                "attacking_team": attacking_team
            },
            game_id=game.id,
            team_abbr=attacking_team,
            is_primary=True
        ))

    # Bottom half in rebounds allowed
    if defense.reb_rank >= 16:
        strength = 0.4 + ((defense.reb_rank - 20) * 0.03)
        edges.append(Edge(
            edge_type=EdgeType.SCHEME,
            description=f"{defending_team} ranks {defense.reb_rank}th in rebounds allowed "
                       f"({defense.reb_allowed:.1f} RPG) - rebounding opportunity for {attacking_team}",
            affected_stats=["rebounds", "pts_rebs_asts", "pts_rebs", "rebs_asts", "double_double"],
            strength=min(strength, 0.8),
            supporting_data={
                "defensive_stat": "rebounds",
                "rank": defense.reb_rank,
                "allowed": defense.reb_allowed,
                "defending_team": defending_team,
                "attacking_team": attacking_team
            },
            game_id=game.id,
            team_abbr=attacking_team,
            is_primary=True
        ))

    # Bottom 10 in assists allowed
    if defense.ast_rank >= 16:
        strength = 0.4 + ((defense.ast_rank - 20) * 0.03)
        edges.append(Edge(
            edge_type=EdgeType.SCHEME,
            description=f"{defending_team} ranks {defense.ast_rank}th in assists allowed "
                       f"({defense.ast_allowed:.1f} APG) - playmaking opportunity for {attacking_team}",
            affected_stats=["assists", "pts_rebs_asts", "pts_asts", "rebs_asts", "double_double"],
            strength=min(strength, 0.8),
            supporting_data={
                "defensive_stat": "assists",
                "rank": defense.ast_rank,
                "allowed": defense.ast_allowed,
                "defending_team": defending_team,
                "attacking_team": attacking_team
            },
            game_id=game.id,
            team_abbr=attacking_team,
            is_primary=True
        ))

    # Bottom 10 in 3PM allowed
    if defense.fg3m_rank >= 16:
        strength = 0.4 + ((defense.fg3m_rank - 20) * 0.03)
        edges.append(Edge(
            edge_type=EdgeType.SCHEME,
            description=f"{defending_team} ranks {defense.fg3m_rank}th in 3PM allowed "
                       f"({defense.fg3m_allowed:.1f} per game) - 3PT opportunity for {attacking_team}",
            affected_stats=["threes", "points"],
            strength=min(strength, 0.8),
            supporting_data={
                "defensive_stat": "threes",
                "rank": defense.fg3m_rank,
                "allowed": defense.fg3m_allowed,
                "defending_team": defending_team,
                "attacking_team": attacking_team
            },
            game_id=game.id,
            team_abbr=attacking_team,
            is_primary=True
        ))

    return edges


def find_pace_edges(games: List[Game]) -> List[Edge]:
    """Discover edges from pace mismatches and game environments.

    Args:
        games: Today's games

    Returns:
        List of pace-based Edge objects
    """
    edges = []
    team_stats_df = get_team_stats()

    if team_stats_df.empty:
        return edges

    for game in games:
        # Get pace for both teams
        home_row = team_stats_df[team_stats_df["TEAM_ID"] == game.home_team_id]
        away_row = team_stats_df[team_stats_df["TEAM_ID"] == game.away_team_id]

        if home_row.empty or away_row.empty:
            continue

        home_pace = home_row.iloc[0].get("PACE", 100.0)
        away_pace = away_row.iloc[0].get("PACE", 100.0)
        avg_pace = (home_pace + away_pace) / 2

        # High pace game (both teams fast)
        if avg_pace >= 102.0:
            strength = 0.3 + ((avg_pace - 100) * 0.05)
            edges.append(Edge(
                edge_type=EdgeType.PACE,
                description=f"High pace environment ({avg_pace:.1f}) - "
                           f"increased counting stat opportunities",
                affected_stats=["points", "rebounds", "assists", "threes",
                               "pts_rebs_asts", "pts_asts", "pts_rebs", "rebs_asts"],
                strength=min(strength, 0.6),
                supporting_data={
                    "home_pace": home_pace,
                    "away_pace": away_pace,
                    "combined_pace": avg_pace,
                    "pace_type": "high"
                },
                game_id=game.id,
                team_abbr=game.home_team_abbr,  # Both teams benefit
                is_primary=False  # Pace is usually a secondary edge
            ))

        # Pace mismatch (one team much faster)
        pace_diff = abs(home_pace - away_pace)
        if pace_diff >= 3.0:
            fast_team = game.home_team_abbr if home_pace > away_pace else game.away_team_abbr
            slow_team = game.away_team_abbr if home_pace > away_pace else game.home_team_abbr

            edges.append(Edge(
                edge_type=EdgeType.PACE,
                description=f"Pace mismatch: {fast_team} ({max(home_pace, away_pace):.1f}) "
                           f"vs {slow_team} ({min(home_pace, away_pace):.1f})",
                affected_stats=["points", "rebounds", "assists"],
                strength=0.3 + (pace_diff * 0.05),
                supporting_data={
                    "fast_team": fast_team,
                    "slow_team": slow_team,
                    "pace_difference": pace_diff
                },
                game_id=game.id,
                team_abbr=fast_team,
                is_primary=False
            ))

    logger.info("found_pace_edges", count=len(edges))
    return edges


def find_positional_edges(
    player: Player,
    opponent_defense: TeamDefenseStats,
    game: Game
) -> List[Edge]:
    """Find edges based on player position vs opponent's position defense.

    Args:
        player: Player to analyze
        opponent_defense: Opponent's defensive stats
        game: Game context

    Returns:
        List of positional Edge objects
    """
    edges = []
    position = player.position.upper()

    # Center vs poor interior defense
    if "C" in position:
        # Check paint defense
        if opponent_defense.reb_rank >= 16:
            edges.append(Edge(
                edge_type=EdgeType.SCHEME,
                description=f"{player.name} (C) vs {opponent_defense.team_abbr}'s "
                           f"weak interior defense (#{opponent_defense.reb_rank} reb allowed)",
                affected_stats=["rebounds", "points", "pts_rebs", "double_double"],
                strength=0.5 + ((opponent_defense.reb_rank - 20) * 0.03),
                supporting_data={
                    "player": player.name,
                    "position": position,
                    "matchup_type": "center_vs_weak_interior",
                    "opponent_reb_rank": opponent_defense.reb_rank
                },
                benefiting_player_ids=[player.id],
                game_id=game.id,
                team_abbr=player.team_abbr,
                is_primary=True
            ))

    # Guard vs poor perimeter defense
    if "G" in position:
        if opponent_defense.fg3m_rank >= 16:
            edges.append(Edge(
                edge_type=EdgeType.SCHEME,
                description=f"{player.name} (G) vs {opponent_defense.team_abbr}'s "
                           f"weak perimeter defense (#{opponent_defense.fg3m_rank} 3PM allowed)",
                affected_stats=["threes", "points"],
                strength=0.5 + ((opponent_defense.fg3m_rank - 20) * 0.03),
                supporting_data={
                    "player": player.name,
                    "position": position,
                    "matchup_type": "guard_vs_weak_perimeter",
                    "opponent_3pm_rank": opponent_defense.fg3m_rank
                },
                benefiting_player_ids=[player.id],
                game_id=game.id,
                team_abbr=player.team_abbr,
                is_primary=True
            ))

    return edges

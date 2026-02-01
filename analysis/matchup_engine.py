"""
Matchup engine that maps discovered edges to specific player props.
This is the core component that connects edges to betting opportunities.
"""
from typing import Dict, List, Optional, Tuple
import structlog

from config.settings import get_settings
from config.constants import STAT_TO_PROP_MAP
from data.models.schemas import (
    Edge, Game, Player, Prop, PropAnalysis, Team,
    TeamDefenseStats, ScheduleContext, PlayerGameLog
)
from data.collectors.nba_stats import (
    get_player_game_logs, get_team_defensive_stats, enrich_player_with_stats,
    calculate_weighted_averages, get_player_vs_opponent_history
)
from data.collectors.schedule import get_schedule_context

logger = structlog.get_logger()
settings = get_settings()


def match_edges_to_props(
    edges: List[Edge],
    props: List[Prop],
    games: List[Game]
) -> List[PropAnalysis]:
    """Match discovered edges to available props.

    This is the core matching algorithm that:
    1. Groups edges by game/team
    2. Finds props that align with those edges
    3. Creates PropAnalysis objects with full context

    Args:
        edges: All discovered edges
        props: Available props from sportsbooks
        games: Today's games

    Returns:
        List of PropAnalysis objects ready for validation
    """
    analyses = []

    # Build player to team mapping from league stats
    from data.collectors.nba_stats import get_league_player_stats
    league_stats = get_league_player_stats()
    player_name_to_team: Dict[str, str] = {}
    if not league_stats.empty:
        for _, row in league_stats.iterrows():
            name = row.get("PLAYER_NAME", "")
            team = row.get("TEAM_ABBREVIATION", "UNK")
            if name and team:
                player_name_to_team[name] = team

    # Group edges by benefiting team
    edges_by_team: Dict[str, List[Edge]] = {}
    for edge in edges:
        team = edge.team_abbr
        if team not in edges_by_team:
            edges_by_team[team] = []
        edges_by_team[team].append(edge)

    # Group props by player and enrich with team info
    props_by_player: Dict[str, List[Prop]] = {}
    for prop in props:
        name = prop.player_name
        # Try to find team for this player
        if prop.team_abbr == "UNK" and name in player_name_to_team:
            prop.team_abbr = player_name_to_team[name]
        if name not in props_by_player:
            props_by_player[name] = []
        props_by_player[name].append(prop)

    logger.info("enriched_props_with_teams",
                total_players=len(props_by_player),
                with_teams=sum(1 for name, pl in props_by_player.items()
                              if any(p.team_abbr != "UNK" for p in pl)))

    # For each team with edges, find matching player props
    for team_abbr, team_edges in edges_by_team.items():
        # Find game for this team
        game = _find_game_for_team(team_abbr, games)
        if not game:
            continue

        # Get opponent
        opponent_abbr = (game.away_team_abbr if game.home_team_abbr == team_abbr
                        else game.home_team_abbr)

        # Find players on this team with props
        team_players_with_props = [
            (name, player_props) for name, player_props in props_by_player.items()
            if any(p.team_abbr == team_abbr for p in player_props)
        ]

        for player_name, player_props in team_players_with_props:
            # Find edges that affect this player's props
            for prop in player_props:
                matching_edges = _find_edges_for_prop(prop, team_edges)
                if not matching_edges:
                    continue

                # Create analysis
                analysis = _create_prop_analysis(
                    prop=prop,
                    edges=matching_edges,
                    game=game,
                    opponent_abbr=opponent_abbr
                )
                if analysis:
                    analyses.append(analysis)

    logger.info("matched_props_to_edges", total_analyses=len(analyses))
    return analyses


def _find_game_for_team(team_abbr: str, games: List[Game]) -> Optional[Game]:
    """Find the game a team is playing in.

    Args:
        team_abbr: Team abbreviation
        games: List of games

    Returns:
        Game object or None
    """
    for game in games:
        if game.home_team_abbr == team_abbr or game.away_team_abbr == team_abbr:
            return game
    return None


def _find_edges_for_prop(prop: Prop, edges: List[Edge]) -> List[Edge]:
    """Find edges that apply to a specific prop.

    Args:
        prop: The prop bet
        edges: Team's edges

    Returns:
        List of matching edges
    """
    matching = []
    prop_type = prop.prop_type

    for edge in edges:
        # Check if this edge affects the prop's stat type
        if prop_type in edge.affected_stats:
            matching.append(edge)

        # Check if it's a combo prop and any component matches
        if prop_type == "pts_rebs_asts":
            if any(stat in edge.affected_stats for stat in ["points", "rebounds", "assists"]):
                if edge not in matching:
                    matching.append(edge)
        elif prop_type == "pts_asts":
            if any(stat in edge.affected_stats for stat in ["points", "assists"]):
                if edge not in matching:
                    matching.append(edge)
        elif prop_type == "pts_rebs":
            if any(stat in edge.affected_stats for stat in ["points", "rebounds"]):
                if edge not in matching:
                    matching.append(edge)
        elif prop_type == "rebs_asts":
            if any(stat in edge.affected_stats for stat in ["rebounds", "assists"]):
                if edge not in matching:
                    matching.append(edge)

    return matching


def _create_prop_analysis(
    prop: Prop,
    edges: List[Edge],
    game: Game,
    opponent_abbr: str
) -> Optional[PropAnalysis]:
    """Create a full PropAnalysis for a prop with matching edges.

    Args:
        prop: The prop bet
        edges: Matching edges
        game: Game context
        opponent_abbr: Opponent abbreviation

    Returns:
        PropAnalysis object or None if insufficient data
    """
    # This would normally look up the player, but we may only have name
    # Create a minimal player object
    player = Player(
        id=prop.player_id,
        name=prop.player_name,
        team_id=0,
        team_abbr=prop.team_abbr,
        position=""
    )

    # Get opponent defense stats
    opponent_team_id = _get_team_id(opponent_abbr)
    opponent_defense = None
    if opponent_team_id:
        opponent_defense = get_team_defensive_stats(opponent_team_id)

    opponent = Team(
        id=opponent_team_id or 0,
        abbr=opponent_abbr,
        name=opponent_abbr
    )
    if opponent_defense:
        opponent.opp_ppg = opponent_defense.pts_allowed
        opponent.opp_rpg = opponent_defense.reb_allowed
        opponent.opp_apg = opponent_defense.ast_allowed
        opponent.def_rank_pts = opponent_defense.pts_rank
        opponent.def_rank_reb = opponent_defense.reb_rank
        opponent.def_rank_ast = opponent_defense.ast_rank

    # Get player game logs
    game_logs = []
    player_id = prop.player_id
    # If no player_id, try to look up by name
    if not player_id:
        from nba_api.stats.static import players
        all_players = players.get_players()
        for p in all_players:
            if p["full_name"] == prop.player_name:
                player_id = p["id"]
                prop.player_id = player_id  # Cache it
                player.id = player_id
                break
    if player_id:
        game_logs = get_player_game_logs(player_id)

    # Get schedule context
    schedule = get_schedule_context(prop.team_abbr, opponent_abbr)

    # Calculate projections based on averages and edges
    projected_low, projected_high = _calculate_projection_range(
        prop, game_logs, edges
    )

    # Determine direction (over/under)
    direction = _determine_direction(prop, projected_low, projected_high)

    # Calculate initial confidence scores
    edge_strength = sum(e.strength for e in edges) / len(edges) if edges else 0.0

    analysis = PropAnalysis(
        prop=prop,
        player=player,
        opponent=opponent,
        game=game,
        edges=edges,
        player_game_logs=game_logs,
        schedule=schedule,
        projected_low=projected_low,
        projected_high=projected_high,
        projected_mid=(projected_low + projected_high) / 2,
        direction=direction,
        edge_strength_score=edge_strength
    )

    return analysis


def _get_team_id(abbr: str) -> Optional[int]:
    """Get team ID from abbreviation."""
    from config.constants import TEAM_IDS
    return TEAM_IDS.get(abbr)


def _calculate_projection_range(
    prop: Prop,
    logs: List[PlayerGameLog],
    edges: List[Edge]
) -> Tuple[float, float]:
    """Calculate projected stat range based on history and edges.

    Args:
        prop: The prop
        logs: Player's game logs
        edges: Relevant edges

    Returns:
        Tuple of (low, high) projections
    """
    if not logs:
        # No history, use line as baseline
        return (prop.line - 2, prop.line + 2)

    # Calculate averages from different windows
    prop_type = prop.prop_type
    averages = calculate_weighted_averages(logs, prop_type, [5, 10, 15])

    recent = averages.get("last_5", prop.line)
    medium = averages.get("last_10", prop.line)
    season = averages.get("season", prop.line)

    # Weight recent more heavily
    baseline = (recent * 0.5) + (medium * 0.3) + (season * 0.2)

    # Adjust for edges
    edge_adjustment = 0.0
    for edge in edges:
        # Positive edges increase projection
        if edge.strength > 0.5:
            edge_adjustment += (edge.strength - 0.5) * 2  # 0-1 scale

    # Apply adjustment (capped)
    edge_adjustment = min(max(edge_adjustment, -2), 4)
    adjusted_baseline = baseline + edge_adjustment

    # Create range based on player's variance
    if len(logs) >= 5:
        values = _get_stat_values(logs[:10], prop_type)
        if values:
            import statistics
            std = statistics.stdev(values) if len(values) > 1 else 2.0
        else:
            std = 2.0
    else:
        std = 2.0

    return (adjusted_baseline - std, adjusted_baseline + std)


def _get_stat_values(logs: List[PlayerGameLog], prop_type: str) -> List[float]:
    """Extract stat values from logs based on prop type."""
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
    return values


def _determine_direction(
    prop: Prop,
    projected_low: float,
    projected_high: float
) -> str:
    """Determine whether to bet over or under.

    Args:
        prop: The prop
        projected_low: Low projection
        projected_high: High projection

    Returns:
        "over" or "under"
    """
    projected_mid = (projected_low + projected_high) / 2

    if projected_mid > prop.line:
        return "over"
    else:
        return "under"


def enrich_analysis_with_context(analysis: PropAnalysis) -> PropAnalysis:
    """Add additional context to a prop analysis.

    Args:
        analysis: Basic analysis

    Returns:
        Enriched analysis
    """
    # Add historical performance vs this opponent
    if analysis.player.id:
        h2h_logs = get_player_vs_opponent_history(
            analysis.player.id,
            analysis.opponent.abbr
        )
        if h2h_logs:
            analysis.conditional_splits["vs_opponent"] = {
                "games": len(h2h_logs),
                "avg": _calculate_avg_from_logs(h2h_logs, analysis.prop.prop_type)
            }

    # Add home/away splits
    if analysis.player_game_logs:
        home_games = [g for g in analysis.player_game_logs if g.is_home]
        away_games = [g for g in analysis.player_game_logs if not g.is_home]

        if home_games:
            analysis.conditional_splits["home"] = {
                "games": len(home_games),
                "avg": _calculate_avg_from_logs(home_games, analysis.prop.prop_type)
            }
        if away_games:
            analysis.conditional_splits["away"] = {
                "games": len(away_games),
                "avg": _calculate_avg_from_logs(away_games, analysis.prop.prop_type)
            }

    return analysis


def _calculate_avg_from_logs(logs: List[PlayerGameLog], prop_type: str) -> float:
    """Calculate average stat from logs."""
    values = _get_stat_values(logs, prop_type)
    return sum(values) / len(values) if values else 0.0

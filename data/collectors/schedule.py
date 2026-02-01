"""
Schedule and rest tracking.
Calculates rest days, back-to-backs, travel distance, and schedule advantages.
"""
import math
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import structlog

from config.settings import get_settings
from config.constants import TEAM_IDS, TEAM_LOCATIONS, TEAM_ID_TO_ABBR
from data.models.schemas import Game, ScheduleContext, Team
from data.cache import get_cache
from data.collectors.nba_stats import get_todays_games

logger = structlog.get_logger()
settings = get_settings()
cache = get_cache()


def _haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance between two lat/lon coordinates in miles.

    Args:
        coord1: (latitude, longitude) of first point
        coord2: (latitude, longitude) of second point

    Returns:
        Distance in miles
    """
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 3959  # Earth's radius in miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def get_team_last_game_date(team_abbr: str, before_date: date) -> Optional[date]:
    """Find when a team last played before a given date.

    Args:
        team_abbr: Team abbreviation
        before_date: Look for games before this date

    Returns:
        Date of last game or None
    """
    cache_key = f"last_game:{team_abbr}:{before_date.isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Check previous days (up to 7)
    for days_back in range(1, 8):
        check_date = before_date - timedelta(days=days_back)
        games = get_todays_games(check_date)

        for game in games:
            if game.home_team_abbr == team_abbr or game.away_team_abbr == team_abbr:
                cache.cache_schedule(cache_key, check_date)
                return check_date

    return None


def calculate_days_rest(team_abbr: str, game_date: Optional[date] = None) -> int:
    """Calculate days of rest for a team.

    Args:
        team_abbr: Team abbreviation
        game_date: Date of upcoming game. Defaults to today.

    Returns:
        Number of rest days (0 = back-to-back)
    """
    if game_date is None:
        game_date = date.today()

    last_game = get_team_last_game_date(team_abbr, game_date)
    if last_game is None:
        return 3  # Assume normal rest if no recent game found

    days = (game_date - last_game).days - 1  # -1 because we want rest days, not elapsed days
    return max(0, days)


def is_back_to_back(team_abbr: str, game_date: Optional[date] = None) -> bool:
    """Check if team is on back-to-back.

    Args:
        team_abbr: Team abbreviation
        game_date: Date of upcoming game

    Returns:
        True if this is second night of B2B
    """
    return calculate_days_rest(team_abbr, game_date) == 0


def get_games_in_last_n_days(team_abbr: str, n_days: int = 7) -> int:
    """Count how many games a team has played in last N days.

    Args:
        team_abbr: Team abbreviation
        n_days: Number of days to look back

    Returns:
        Number of games played
    """
    count = 0
    today = date.today()

    for days_back in range(1, n_days + 1):
        check_date = today - timedelta(days=days_back)
        games = get_todays_games(check_date)

        for game in games:
            if game.home_team_abbr == team_abbr or game.away_team_abbr == team_abbr:
                count += 1
                break  # Only count once per day

    return count


def calculate_travel_distance(
    team_abbr: str,
    game_date: Optional[date] = None
) -> float:
    """Calculate approximate travel distance for team's recent games.

    Args:
        team_abbr: Team abbreviation
        game_date: Reference date

    Returns:
        Total travel distance in miles (last 3 games)
    """
    if game_date is None:
        game_date = date.today()

    team_location = TEAM_LOCATIONS.get(team_abbr)
    if not team_location:
        return 0.0

    total_distance = 0.0
    current_location = team_location
    games_checked = 0

    # Check last 3 game locations
    for days_back in range(1, 10):
        if games_checked >= 3:
            break

        check_date = game_date - timedelta(days=days_back)
        games = get_todays_games(check_date)

        for game in games:
            if game.home_team_abbr == team_abbr:
                # Home game
                game_location = TEAM_LOCATIONS.get(game.home_team_abbr)
            elif game.away_team_abbr == team_abbr:
                # Away game
                game_location = TEAM_LOCATIONS.get(game.home_team_abbr)  # Traveled to opponent
            else:
                continue

            if game_location:
                distance = _haversine_distance(current_location, game_location)
                total_distance += distance
                current_location = game_location
                games_checked += 1
                break

    return total_distance


def get_schedule_context(
    team_abbr: str,
    opponent_abbr: str,
    game_date: Optional[date] = None
) -> ScheduleContext:
    """Get complete schedule context for a team facing an opponent.

    Args:
        team_abbr: Team abbreviation
        opponent_abbr: Opponent abbreviation
        game_date: Game date (defaults to today)

    Returns:
        ScheduleContext object with rest, travel, and advantage info
    """
    if game_date is None:
        game_date = date.today()

    team_id = TEAM_IDS.get(team_abbr, 0)
    days_rest = calculate_days_rest(team_abbr, game_date)
    opp_days_rest = calculate_days_rest(opponent_abbr, game_date)

    # Determine if home game
    games = get_todays_games(game_date)
    is_home = False
    for game in games:
        if game.home_team_abbr == team_abbr:
            is_home = True
            break

    context = ScheduleContext(
        team_id=team_id,
        team_abbr=team_abbr,
        days_rest=days_rest,
        is_back_to_back=(days_rest == 0),
        games_in_last_7_days=get_games_in_last_n_days(team_abbr, 7),
        is_home=is_home,
        travel_miles=calculate_travel_distance(team_abbr, game_date),
        timezone_changes=0,  # Would need more complex calculation
        opponent_days_rest=opp_days_rest,
        opponent_is_b2b=(opp_days_rest == 0),
        rest_advantage=days_rest - opp_days_rest
    )

    return context


def get_all_schedule_contexts(games: List[Game]) -> Dict[str, ScheduleContext]:
    """Get schedule context for all teams playing today.

    Args:
        games: List of today's games

    Returns:
        Dict mapping team abbreviation to ScheduleContext
    """
    contexts = {}

    for game in games:
        # Home team
        home_context = get_schedule_context(
            game.home_team_abbr,
            game.away_team_abbr,
            game.date
        )
        contexts[game.home_team_abbr] = home_context

        # Away team
        away_context = get_schedule_context(
            game.away_team_abbr,
            game.home_team_abbr,
            game.date
        )
        contexts[game.away_team_abbr] = away_context

    return contexts


def identify_schedule_edges(games: List[Game]) -> List[Dict]:
    """Identify games with significant schedule advantages.

    Args:
        games: List of today's games

    Returns:
        List of schedule edge dictionaries
    """
    edges = []
    contexts = get_all_schedule_contexts(games)

    for game in games:
        home_ctx = contexts.get(game.home_team_abbr)
        away_ctx = contexts.get(game.away_team_abbr)

        if not home_ctx or not away_ctx:
            continue

        # Significant rest advantage (2+ days)
        if home_ctx.rest_advantage >= 2:
            edges.append({
                "type": "schedule",
                "subtype": "rest_advantage",
                "team": game.home_team_abbr,
                "opponent": game.away_team_abbr,
                "advantage": home_ctx.rest_advantage,
                "description": f"{game.home_team_abbr} has {home_ctx.rest_advantage} more rest days than {game.away_team_abbr}",
                "strength": min(0.3 + (home_ctx.rest_advantage * 0.1), 0.7)
            })
        elif away_ctx.rest_advantage >= 2:
            edges.append({
                "type": "schedule",
                "subtype": "rest_advantage",
                "team": game.away_team_abbr,
                "opponent": game.home_team_abbr,
                "advantage": away_ctx.rest_advantage,
                "description": f"{game.away_team_abbr} has {away_ctx.rest_advantage} more rest days than {game.home_team_abbr}",
                "strength": min(0.3 + (away_ctx.rest_advantage * 0.1), 0.7)
            })

        # Back-to-back fatigue
        if home_ctx.is_back_to_back and not away_ctx.is_back_to_back:
            edges.append({
                "type": "schedule",
                "subtype": "b2b_fatigue",
                "team": game.home_team_abbr,
                "opponent": game.away_team_abbr,
                "advantage": -1,
                "description": f"{game.home_team_abbr} on B2B, {game.away_team_abbr} rested",
                "strength": 0.5
            })
        elif away_ctx.is_back_to_back and not home_ctx.is_back_to_back:
            edges.append({
                "type": "schedule",
                "subtype": "b2b_fatigue",
                "team": game.away_team_abbr,
                "opponent": game.home_team_abbr,
                "advantage": -1,
                "description": f"{game.away_team_abbr} on B2B, {game.home_team_abbr} rested",
                "strength": 0.5
            })

        # Heavy schedule (4+ games in 7 days)
        if home_ctx.games_in_last_7_days >= 4:
            edges.append({
                "type": "schedule",
                "subtype": "heavy_schedule",
                "team": game.home_team_abbr,
                "opponent": game.away_team_abbr,
                "games_in_week": home_ctx.games_in_last_7_days,
                "description": f"{game.home_team_abbr} playing {home_ctx.games_in_last_7_days} games in last 7 days",
                "strength": 0.4
            })
        if away_ctx.games_in_last_7_days >= 4:
            edges.append({
                "type": "schedule",
                "subtype": "heavy_schedule",
                "team": game.away_team_abbr,
                "opponent": game.home_team_abbr,
                "games_in_week": away_ctx.games_in_last_7_days,
                "description": f"{game.away_team_abbr} playing {away_ctx.games_in_last_7_days} games in last 7 days",
                "strength": 0.4
            })

    logger.info("identified_schedule_edges", count=len(edges))
    return edges

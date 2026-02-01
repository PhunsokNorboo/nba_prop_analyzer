"""
Props scraper for FanDuel and DraftKings player props.
Uses The Odds API as primary source with scraping fallback.
"""
import time
from datetime import date, datetime
from typing import Dict, List, Optional
import requests
import structlog

from config.settings import get_settings
from config.constants import PROP_TYPES, BOOKS
from data.models.schemas import Prop, Game
from data.cache import get_cache

logger = structlog.get_logger()
settings = get_settings()
cache = get_cache()

# The Odds API endpoints
ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def _rate_limit():
    """Apply rate limiting."""
    time.sleep(settings.odds_api_delay)


def _normalize_prop_type(raw_type: str) -> Optional[str]:
    """Normalize prop type names from different sources.

    Args:
        raw_type: Raw prop type string from API/scraper

    Returns:
        Normalized prop type or None if not supported
    """
    raw_lower = raw_type.lower().replace(" ", "_").replace("-", "_")

    for normalized, variants in PROP_TYPES.items():
        if raw_lower in variants or normalized in raw_lower:
            return normalized

    return None


def _american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return (american / 100) + 1
    else:
        return (100 / abs(american)) + 1


def get_props_from_odds_api(sport_key: str = "basketball_nba") -> List[Prop]:
    """Fetch player props from The Odds API.

    Args:
        sport_key: Sport identifier

    Returns:
        List of Prop objects
    """
    api_key = settings.odds_api_key
    if not api_key:
        logger.warning("no_odds_api_key", msg="ODDS_API_KEY not set, skipping API fetch")
        return []

    cache_key = f"props_api:{date.today().isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    props = []

    try:
        # Get list of events (games) first
        _rate_limit()
        events_url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
        events_resp = requests.get(
            events_url,
            params={"apiKey": api_key},
            timeout=30
        )
        events_resp.raise_for_status()
        events = events_resp.json()

        logger.info("fetched_events", count=len(events))

        # For each event, get player props
        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue

            # Check if game is today
            commence_time = event.get("commence_time", "")
            if commence_time:
                try:
                    game_date = datetime.fromisoformat(commence_time.replace("Z", "+00:00")).date()
                    if game_date != date.today():
                        continue
                except:
                    pass

            _rate_limit()
            props_url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds"
            props_resp = requests.get(
                props_url,
                params={
                    "apiKey": api_key,
                    "regions": "us",
                    "markets": "player_points,player_rebounds,player_assists,player_threes",
                    "oddsFormat": "american",
                    "bookmakers": "fanduel,draftkings"
                },
                timeout=30
            )

            if props_resp.status_code != 200:
                continue

            props_data = props_resp.json()
            event_props = _parse_odds_api_props(props_data, event)
            props.extend(event_props)

        logger.info("fetched_props", count=len(props))
        cache.cache_props(cache_key, props)
        return props

    except requests.RequestException as e:
        logger.error("odds_api_request_failed", error=str(e))
        return []
    except Exception as e:
        logger.error("odds_api_error", error=str(e))
        return []


def _parse_odds_api_props(data: dict, event: dict) -> List[Prop]:
    """Parse props from The Odds API response.

    Args:
        data: API response for props
        event: Event data for context

    Returns:
        List of Prop objects
    """
    props = []
    bookmakers = data.get("bookmakers", [])

    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")
    game_id = event.get("id", "")

    for bookmaker in bookmakers:
        book_name = bookmaker.get("key", "").lower()
        if book_name not in ["fanduel", "draftkings"]:
            continue

        book_display = BOOKS.get(book_name, book_name.title())

        for market in bookmaker.get("markets", []):
            market_key = market.get("key", "")
            prop_type = _normalize_prop_type(market_key)

            if not prop_type:
                continue

            for outcome in market.get("outcomes", []):
                player_name = outcome.get("description", "")
                point = outcome.get("point")
                price = outcome.get("price")
                name = outcome.get("name", "").lower()

                if not all([player_name, point is not None, price]):
                    continue

                # Determine if this is over or under line
                # The API typically gives separate outcomes for over/under
                if name == "over":
                    over_odds = price
                    under_odds = -110  # Default, would need to find matching under
                elif name == "under":
                    under_odds = price
                    over_odds = -110  # Default
                else:
                    continue

                # Determine player's team
                # This is simplified - would need player lookup for accuracy
                team_abbr = "UNK"
                opponent_abbr = "UNK"
                is_home = True

                prop = Prop(
                    player_id=0,  # Would need player ID lookup
                    player_name=player_name,
                    team_abbr=team_abbr,
                    game_id=game_id,
                    opponent_abbr=opponent_abbr,
                    prop_type=prop_type,
                    line=float(point),
                    over_odds=over_odds,
                    under_odds=under_odds,
                    book=book_display,
                    is_home=is_home
                )
                props.append(prop)

    return props


def scrape_draftkings_props() -> List[Prop]:
    """Scrape player props from DraftKings.

    Note: This is a placeholder. Actual implementation would need to:
    1. Navigate to DK NBA player props page
    2. Parse the HTML/JSON for props
    3. Handle dynamic content (may need Selenium)

    Returns:
        List of Prop objects
    """
    logger.info("draftkings_scrape_placeholder", msg="DK scraping not implemented")
    return []


def scrape_fanduel_props() -> List[Prop]:
    """Scrape player props from FanDuel.

    Note: This is a placeholder for the same reasons as DK.

    Returns:
        List of Prop objects
    """
    logger.info("fanduel_scrape_placeholder", msg="FD scraping not implemented")
    return []


def get_all_props_for_games(games: List[Game]) -> List[Prop]:
    """Get all player props for today's games.

    Tries The Odds API first, falls back to scraping if needed.

    Args:
        games: List of today's games

    Returns:
        List of Prop objects
    """
    # Try API first
    # Note: The Odds API already filters to today's games via date check,
    # so we don't need to filter again (game IDs differ between APIs)
    props = get_props_from_odds_api()

    if props:
        logger.info("props_from_api", count=len(props))
        return props

    # Fallback to scraping
    logger.info("falling_back_to_scraping")
    dk_props = scrape_draftkings_props()
    fd_props = scrape_fanduel_props()

    all_props = dk_props + fd_props
    return all_props


def filter_props_by_games(props: List[Prop], games: List[Game]) -> List[Prop]:
    """Filter props to only include games from today's slate.

    Args:
        props: All fetched props
        games: Today's games

    Returns:
        Filtered props
    """
    game_ids = {g.id for g in games}
    team_abbrs = set()
    for g in games:
        team_abbrs.add(g.home_team_abbr)
        team_abbrs.add(g.away_team_abbr)

    filtered = []
    for prop in props:
        # Match by game ID or team
        if prop.game_id in game_ids:
            filtered.append(prop)
        elif prop.team_abbr in team_abbrs:
            filtered.append(prop)

    return filtered


def filter_props_by_odds(props: List[Prop], max_juice: int = -140) -> List[Prop]:
    """Filter out props with odds worse than threshold.

    Args:
        props: List of props
        max_juice: Maximum acceptable odds (e.g., -140)

    Returns:
        Filtered props
    """
    filtered = []
    for prop in props:
        # Check if either over or under meets threshold
        if prop.over_odds >= max_juice or prop.under_odds >= max_juice:
            filtered.append(prop)

    logger.info("filtered_props_by_odds", original=len(props), filtered=len(filtered))
    return filtered


def filter_props_by_type(props: List[Prop], allowed_types: List[str]) -> List[Prop]:
    """Filter props to only allowed types.

    Args:
        props: List of props
        allowed_types: List of allowed prop type strings

    Returns:
        Filtered props
    """
    return [p for p in props if p.prop_type in allowed_types]


def find_best_line(props: List[Prop], player_name: str, prop_type: str) -> Optional[Prop]:
    """Find the best line for a specific player/prop across books.

    Args:
        player_name: Player name
        prop_type: Prop type

    Returns:
        Prop with best odds, or None
    """
    matching = [
        p for p in props
        if p.player_name.lower() == player_name.lower()
        and p.prop_type == prop_type
    ]

    if not matching:
        return None

    # Sort by best over odds (higher is better for the bettor)
    matching.sort(key=lambda p: p.over_odds, reverse=True)
    return matching[0]


def group_props_by_player(props: List[Prop]) -> Dict[str, List[Prop]]:
    """Group props by player name.

    Args:
        props: List of props

    Returns:
        Dict mapping player name to their props
    """
    grouped: Dict[str, List[Prop]] = {}
    for prop in props:
        name = prop.player_name
        if name not in grouped:
            grouped[name] = []
        grouped[name].append(prop)

    return grouped

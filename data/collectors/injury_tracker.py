"""
Injury tracking and reporting.
Fetches injury data from ESPN and other sources.
"""
import time
from datetime import date, datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
import structlog

from config.settings import get_settings
from config.constants import TEAM_IDS, TEAM_NAMES
from data.models.schemas import Injury, InjuryStatus
from data.cache import get_cache

logger = structlog.get_logger()
settings = get_settings()
cache = get_cache()

# ESPN injury report URL
ESPN_INJURIES_URL = "https://www.espn.com/nba/injuries"

# Rotowire NBA injuries
ROTOWIRE_URL = "https://www.rotowire.com/basketball/nba-lineups.php"


def _rate_limit():
    """Apply rate limiting."""
    time.sleep(settings.scrape_delay)


def _parse_injury_status(status_text: str) -> str:
    """Parse injury status from text.

    Args:
        status_text: Raw status text

    Returns:
        Normalized status string
    """
    status_lower = status_text.lower()

    if "out" in status_lower:
        return InjuryStatus.OUT.value
    elif "doubtful" in status_lower:
        return InjuryStatus.DOUBTFUL.value
    elif "questionable" in status_lower:
        return InjuryStatus.QUESTIONABLE.value
    elif "probable" in status_lower:
        return InjuryStatus.PROBABLE.value
    elif "day-to-day" in status_lower or "day to day" in status_lower:
        return InjuryStatus.DAY_TO_DAY.value
    else:
        return InjuryStatus.AVAILABLE.value


def get_espn_injuries() -> Dict[str, List[Injury]]:
    """Fetch injury reports from ESPN.

    Returns:
        Dict mapping team abbreviation to list of injuries
    """
    cache_key = f"espn_injuries:{date.today().isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    injuries_by_team: Dict[str, List[Injury]] = {}

    try:
        _rate_limit()
        response = requests.get(
            ESPN_INJURIES_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=30
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Find injury tables (ESPN structure may vary)
        # This is a simplified parser - actual structure needs verification
        tables = soup.find_all("table", class_="Table")

        for table in tables:
            # Try to identify team from table header
            header = table.find_previous("h2")
            if not header:
                continue

            team_name = header.get_text(strip=True)
            team_abbr = _team_name_to_abbr(team_name)
            if not team_abbr:
                continue

            team_id = TEAM_IDS.get(team_abbr, 0)
            injuries_by_team[team_abbr] = []

            # Parse rows
            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                player_name = cells[0].get_text(strip=True)
                injury_type = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                status_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""

                injury = Injury(
                    player_id=0,  # Would need lookup
                    player_name=player_name,
                    team_id=team_id,
                    team_abbr=team_abbr,
                    status=_parse_injury_status(status_text),
                    injury_type=injury_type,
                    notes=status_text
                )
                injuries_by_team[team_abbr].append(injury)

        logger.info("fetched_espn_injuries",
                    teams=len(injuries_by_team),
                    total=sum(len(v) for v in injuries_by_team.values()))

        cache.cache_injuries(cache_key, injuries_by_team)
        return injuries_by_team

    except requests.RequestException as e:
        logger.error("espn_injuries_fetch_failed", error=str(e))
        return {}
    except Exception as e:
        logger.error("espn_injuries_parse_error", error=str(e))
        return {}


def _team_name_to_abbr(team_name: str) -> Optional[str]:
    """Convert team name to abbreviation.

    Args:
        team_name: Full or partial team name

    Returns:
        Team abbreviation or None
    """
    name_lower = team_name.lower()

    for abbr, full_name in TEAM_NAMES.items():
        if full_name.lower() in name_lower or name_lower in full_name.lower():
            return abbr

    # Check individual words
    for abbr, full_name in TEAM_NAMES.items():
        words = full_name.lower().split()
        for word in words:
            if word in name_lower:
                return abbr

    return None


def get_injury_report() -> Dict[str, List[Injury]]:
    """Get comprehensive injury report from all sources.

    Returns:
        Dict mapping team abbreviation to list of injuries
    """
    # Primary source: ESPN
    injuries = get_espn_injuries()

    # Could add additional sources here (Rotowire, NBA official, etc.)

    return injuries


def get_team_injuries(team_abbr: str) -> List[Injury]:
    """Get injuries for a specific team.

    Args:
        team_abbr: Team abbreviation

    Returns:
        List of injuries for that team
    """
    all_injuries = get_injury_report()
    return all_injuries.get(team_abbr, [])


def get_key_injuries(
    team_abbr: str,
    min_usage: float = 15.0,
    min_minutes: float = 20.0
) -> List[Injury]:
    """Get injuries to key players (high usage/minutes).

    Args:
        team_abbr: Team abbreviation
        min_usage: Minimum usage rate to be considered "key"
        min_minutes: Minimum minutes per game

    Returns:
        List of key player injuries
    """
    injuries = get_team_injuries(team_abbr)

    # Filter to OUT or DOUBTFUL players with significant roles
    key_injuries = [
        inj for inj in injuries
        if inj.status in [InjuryStatus.OUT.value, InjuryStatus.DOUBTFUL.value]
        and (inj.usage_rate >= min_usage or inj.minutes_per_game >= min_minutes)
    ]

    return key_injuries


def get_players_out(team_abbr: str) -> List[str]:
    """Get list of player names definitely out.

    Args:
        team_abbr: Team abbreviation

    Returns:
        List of player names who are OUT
    """
    injuries = get_team_injuries(team_abbr)
    return [
        inj.player_name for inj in injuries
        if inj.status == InjuryStatus.OUT.value
    ]


def get_questionable_players(team_abbr: str) -> List[str]:
    """Get list of questionable players (may or may not play).

    Args:
        team_abbr: Team abbreviation

    Returns:
        List of player names who are QUESTIONABLE or DAY_TO_DAY
    """
    injuries = get_team_injuries(team_abbr)
    uncertain_statuses = [
        InjuryStatus.QUESTIONABLE.value,
        InjuryStatus.DAY_TO_DAY.value,
        InjuryStatus.DOUBTFUL.value
    ]
    return [
        inj.player_name for inj in injuries
        if inj.status in uncertain_statuses
    ]


def detect_recent_injuries(days_back: int = 7) -> List[Injury]:
    """Detect injuries that occurred recently (potential inflection points).

    Args:
        days_back: Number of days to look back

    Returns:
        List of recent injuries
    """
    all_injuries = get_injury_report()
    recent = []

    for team_injuries in all_injuries.values():
        for inj in team_injuries:
            if inj.injury_date:
                days_ago = (date.today() - inj.injury_date).days
                if days_ago <= days_back:
                    recent.append(inj)

    return recent


def is_player_available(player_name: str, team_abbr: str) -> bool:
    """Check if a player is available to play.

    Args:
        player_name: Player name
        team_abbr: Team abbreviation

    Returns:
        True if player is available (not OUT or DOUBTFUL)
    """
    injuries = get_team_injuries(team_abbr)

    for inj in injuries:
        if player_name.lower() in inj.player_name.lower():
            if inj.status in [InjuryStatus.OUT.value, InjuryStatus.DOUBTFUL.value]:
                return False

    return True


def get_injury_impact_on_team(team_abbr: str) -> Dict[str, float]:
    """Calculate the statistical impact of current injuries on a team.

    Args:
        team_abbr: Team abbreviation

    Returns:
        Dict with estimated stat losses (points, rebounds, assists lost)
    """
    injuries = get_team_injuries(team_abbr)
    out_players = [
        inj for inj in injuries
        if inj.status == InjuryStatus.OUT.value
    ]

    # Sum up the stats lost from injured players
    # Note: This would need actual player stats to be accurate
    # For now, returns estimates based on injury.usage_rate/minutes
    impact = {
        "points_lost": 0.0,
        "rebounds_lost": 0.0,
        "assists_lost": 0.0,
        "minutes_lost": 0.0
    }

    for inj in out_players:
        # Rough estimates based on minutes
        mpg = inj.minutes_per_game or 20.0
        impact["minutes_lost"] += mpg
        # Average NBA production per minute: ~0.5 pts, ~0.2 reb, ~0.15 ast
        impact["points_lost"] += mpg * 0.5
        impact["rebounds_lost"] += mpg * 0.2
        impact["assists_lost"] += mpg * 0.15

    return impact

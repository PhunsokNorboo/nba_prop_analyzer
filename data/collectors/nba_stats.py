"""
NBA statistics collector using nba_api.
Fetches player stats, team stats, game schedules, and defensive data.
"""
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import structlog

from nba_api.stats.endpoints import (
    scoreboardv2 as scoreboard,
    playergamelog,
    leaguedashplayerstats,
    leaguedashteamstats,
    teamgamelog,
    commonplayerinfo,
    leaguedashptdefend,
)
from nba_api.stats.static import teams, players

from config.settings import get_settings
from config.constants import (
    TEAM_IDS, TEAM_ID_TO_ABBR, CURRENT_SEASON, CURRENT_SEASON_TYPE
)
from data.models.schemas import (
    Player, Team, Game, PlayerGameLog, TeamDefenseStats
)
from data.cache import get_cache

logger = structlog.get_logger()
settings = get_settings()
cache = get_cache()


def _rate_limit():
    """Apply rate limiting between API calls."""
    time.sleep(settings.nba_api_delay)


def get_todays_games(game_date: Optional[date] = None) -> List[Game]:
    """Get all NBA games scheduled for a given date.

    Args:
        game_date: Date to check. Defaults to today.

    Returns:
        List of Game objects
    """
    if game_date is None:
        game_date = date.today()

    cache_key = f"games:{game_date.isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        _rate_limit()
        sb = scoreboard.ScoreboardV2(
            game_date=game_date.strftime("%Y-%m-%d"),
            league_id="00"
        )
        games_df = sb.get_data_frames()[0]

        games = []
        for _, row in games_df.iterrows():
            game = Game(
                id=row["GAME_ID"],
                date=game_date,
                home_team_id=row["HOME_TEAM_ID"],
                away_team_id=row["VISITOR_TEAM_ID"],
                home_team_abbr=TEAM_ID_TO_ABBR.get(row["HOME_TEAM_ID"], "UNK"),
                away_team_abbr=TEAM_ID_TO_ABBR.get(row["VISITOR_TEAM_ID"], "UNK"),
                status=row.get("GAME_STATUS_TEXT", "scheduled")
            )
            games.append(game)

        logger.info("fetched_games", date=str(game_date), count=len(games))
        cache.cache_schedule(cache_key, games)
        return games

    except Exception as e:
        logger.error("failed_fetch_games", date=str(game_date), error=str(e))
        return []


def get_player_game_logs(
    player_id: int,
    season: str = CURRENT_SEASON,
    last_n_games: Optional[int] = None
) -> List[PlayerGameLog]:
    """Get game-by-game stats for a player.

    Args:
        player_id: NBA player ID
        season: Season string (e.g., "2024-25")
        last_n_games: Limit to last N games. None = full season.

    Returns:
        List of PlayerGameLog objects, most recent first
    """
    cache_key = f"player_logs:{player_id}:{season}:{last_n_games}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        _rate_limit()
        log = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            season_type_all_star=CURRENT_SEASON_TYPE
        )
        df = log.get_data_frames()[0]

        if df.empty:
            return []

        # Convert to our schema
        logs = []
        for _, row in df.iterrows():
            try:
                game_date = datetime.strptime(row["GAME_DATE"], "%b %d, %Y").date()
            except:
                game_date = date.today()

            matchup = row.get("MATCHUP", "")
            is_home = "@" not in matchup

            # Extract opponent
            if "@" in matchup:
                opponent_abbr = matchup.split("@")[1].strip()
            elif "vs." in matchup:
                opponent_abbr = matchup.split("vs.")[1].strip()
            else:
                opponent_abbr = "UNK"

            game_log = PlayerGameLog(
                player_id=player_id,
                game_id=row["Game_ID"],
                game_date=game_date,
                opponent_id=0,  # Would need separate lookup
                opponent_abbr=opponent_abbr,
                is_home=is_home,
                minutes=float(row.get("MIN", 0) or 0),
                points=int(row.get("PTS", 0) or 0),
                rebounds=int(row.get("REB", 0) or 0),
                assists=int(row.get("AST", 0) or 0),
                fg3m=int(row.get("FG3M", 0) or 0),
                fgm=int(row.get("FGM", 0) or 0),
                fga=int(row.get("FGA", 0) or 0),
                ftm=int(row.get("FTM", 0) or 0),
                fta=int(row.get("FTA", 0) or 0),
                steals=int(row.get("STL", 0) or 0),
                blocks=int(row.get("BLK", 0) or 0),
                turnovers=int(row.get("TOV", 0) or 0),
                plus_minus=int(row.get("PLUS_MINUS", 0) or 0),
                team_won=row.get("WL", "") == "W"
            )
            logs.append(game_log)

        # Sort by date (most recent first)
        logs.sort(key=lambda x: x.game_date, reverse=True)

        if last_n_games:
            logs = logs[:last_n_games]

        logger.debug("fetched_player_logs", player_id=player_id, count=len(logs))
        cache.cache_stats(cache_key, logs)
        return logs

    except Exception as e:
        logger.error("failed_fetch_player_logs", player_id=player_id, error=str(e))
        return []


def get_league_player_stats(
    season: str = CURRENT_SEASON,
    per_mode: str = "PerGame"
) -> pd.DataFrame:
    """Get league-wide player statistics.

    Args:
        season: Season string
        per_mode: "PerGame" or "Totals"

    Returns:
        DataFrame with all player stats
    """
    cache_key = f"league_player_stats:{season}:{per_mode}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        _rate_limit()
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star=CURRENT_SEASON_TYPE,
            per_mode_detailed=per_mode
        )
        df = stats.get_data_frames()[0]

        logger.info("fetched_league_player_stats", count=len(df))
        cache.cache_stats(cache_key, df)
        return df

    except Exception as e:
        logger.error("failed_fetch_league_stats", error=str(e))
        return pd.DataFrame()


def get_team_stats(
    season: str = CURRENT_SEASON,
    per_mode: str = "PerGame"
) -> pd.DataFrame:
    """Get league-wide team statistics.

    Args:
        season: Season string
        per_mode: "PerGame" or "Totals"

    Returns:
        DataFrame with all team stats
    """
    cache_key = f"team_stats:{season}:{per_mode}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        _rate_limit()
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star=CURRENT_SEASON_TYPE,
            per_mode_detailed=per_mode
        )
        df = stats.get_data_frames()[0]

        logger.info("fetched_team_stats", count=len(df))
        cache.cache_stats(cache_key, df)
        return df

    except Exception as e:
        logger.error("failed_fetch_team_stats", error=str(e))
        return pd.DataFrame()


def get_team_defensive_stats(
    team_id: int,
    last_n_games: Optional[int] = None
) -> Optional[TeamDefenseStats]:
    """Get defensive stats for a team (points/rebounds/assists allowed).

    Args:
        team_id: NBA team ID
        last_n_games: Limit to recent games for trend analysis

    Returns:
        TeamDefenseStats object or None
    """
    cache_key = f"team_defense:{team_id}:{last_n_games}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        # Get team game logs to calculate opponent stats
        _rate_limit()
        log = teamgamelog.TeamGameLog(
            team_id=team_id,
            season=CURRENT_SEASON,
            season_type_all_star=CURRENT_SEASON_TYPE
        )
        df = log.get_data_frames()[0]

        if df.empty:
            return None

        if last_n_games:
            df = df.head(last_n_games)

        # Calculate averages allowed (these are the team's own stats, but
        # we need opponent stats - for now use estimates)
        # In a full implementation, you'd aggregate from play-by-play or
        # opponent game logs
        team_abbr = TEAM_ID_TO_ABBR.get(team_id, "UNK")

        # Get league-wide team stats for rankings
        all_team_stats = get_team_stats()

        # Find this team's defensive stats
        # Note: nba_api has OPP_ columns for opponent stats allowed
        team_row = all_team_stats[all_team_stats["TEAM_ID"] == team_id]

        if team_row.empty:
            return None

        row = team_row.iloc[0]

        # Estimate opponent stats allowed (league average ~115 pts, 44 reb, 25 ast)
        # Teams with negative PLUS_MINUS tend to allow more points
        plus_minus = float(row.get("PLUS_MINUS", 0) or 0)
        league_avg_pts = 115.0
        opp_pts = league_avg_pts - (plus_minus * 0.5)  # Rough estimate
        opp_reb = 44.0 + (1 if plus_minus < 0 else -1)
        opp_ast = 25.0
        opp_fg3m = 12.5

        # Rank teams by PLUS_MINUS (lower = worse defense = higher rank)
        # Rank 1 = best defense (highest plus_minus), Rank 30 = worst defense
        all_team_stats_copy = all_team_stats.copy()
        all_team_stats_copy["_def_rank"] = all_team_stats_copy["PLUS_MINUS"].rank(ascending=True, method="min")
        team_def_rank = int(all_team_stats_copy.loc[all_team_stats_copy["TEAM_ID"] == team_id, "_def_rank"].iloc[0])

        # Use same rank for all categories as approximation
        pts_rank = team_def_rank
        reb_rank = team_def_rank
        ast_rank = team_def_rank
        fg3m_rank = team_def_rank

        defense_stats = TeamDefenseStats(
            team_id=team_id,
            team_abbr=team_abbr,
            pts_allowed=opp_pts,
            reb_allowed=opp_reb,
            ast_allowed=opp_ast,
            fg3m_allowed=opp_fg3m,
            pts_rank=pts_rank,
            reb_rank=reb_rank,
            ast_rank=ast_rank,
            fg3m_rank=fg3m_rank,
            games_sampled=len(df),
            as_of_date=date.today()
        )

        cache.cache_stats(cache_key, defense_stats)
        return defense_stats

    except Exception as e:
        logger.error("failed_fetch_team_defense", team_id=team_id, error=str(e))
        return None


def get_player_info(player_id: int) -> Optional[Player]:
    """Get basic player information.

    Args:
        player_id: NBA player ID

    Returns:
        Player object or None
    """
    cache_key = f"player_info:{player_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        _rate_limit()
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        df = info.get_data_frames()[0]

        if df.empty:
            return None

        row = df.iloc[0]
        team_id = row.get("TEAM_ID", 0)

        player = Player(
            id=player_id,
            name=row.get("DISPLAY_FIRST_LAST", "Unknown"),
            team_id=team_id,
            team_abbr=TEAM_ID_TO_ABBR.get(team_id, "UNK"),
            position=row.get("POSITION", ""),
        )

        cache.cache_stats(cache_key, player)
        return player

    except Exception as e:
        logger.error("failed_fetch_player_info", player_id=player_id, error=str(e))
        return None


def search_player_by_name(name: str) -> Optional[int]:
    """Search for a player ID by name.

    Args:
        name: Player name (partial match supported)

    Returns:
        Player ID or None
    """
    name_lower = name.lower()
    all_players = players.get_players()

    for p in all_players:
        full_name = p["full_name"].lower()
        if name_lower in full_name or full_name in name_lower:
            return p["id"]

    return None


def get_team_id_by_abbr(abbr: str) -> Optional[int]:
    """Get team ID from abbreviation.

    Args:
        abbr: Team abbreviation (e.g., "LAL")

    Returns:
        Team ID or None
    """
    return TEAM_IDS.get(abbr.upper())


def calculate_weighted_averages(
    game_logs: List[PlayerGameLog],
    stat: str,
    windows: List[int] = [5, 10, 15]
) -> Dict[str, float]:
    """Calculate averages over different time windows.

    Args:
        game_logs: List of game logs (most recent first)
        stat: Stat to average ("points", "rebounds", "assists", "fg3m", "pra", etc.)
        windows: List of game window sizes

    Returns:
        Dict with window sizes as keys, averages as values
    """
    if not game_logs:
        return {f"last_{w}": 0.0 for w in windows}

    averages = {}

    for window in windows:
        subset = game_logs[:window]
        if not subset:
            averages[f"last_{window}"] = 0.0
            continue

        if stat == "points":
            values = [g.points for g in subset]
        elif stat == "rebounds":
            values = [g.rebounds for g in subset]
        elif stat == "assists":
            values = [g.assists for g in subset]
        elif stat == "fg3m" or stat == "threes":
            values = [g.fg3m for g in subset]
        elif stat == "pra" or stat == "pts_rebs_asts":
            values = [g.pra for g in subset]
        elif stat == "pts_asts":
            values = [g.pts_asts for g in subset]
        elif stat == "pts_rebs":
            values = [g.pts_rebs for g in subset]
        elif stat == "rebs_asts":
            values = [g.rebs_asts for g in subset]
        elif stat == "minutes":
            values = [g.minutes for g in subset]
        else:
            values = [0]

        averages[f"last_{window}"] = sum(values) / len(values) if values else 0.0

    # Add season average
    if game_logs:
        if stat == "points":
            all_values = [g.points for g in game_logs]
        elif stat == "rebounds":
            all_values = [g.rebounds for g in game_logs]
        elif stat == "assists":
            all_values = [g.assists for g in game_logs]
        elif stat == "fg3m" or stat == "threes":
            all_values = [g.fg3m for g in game_logs]
        elif stat == "pra" or stat == "pts_rebs_asts":
            all_values = [g.pra for g in game_logs]
        elif stat == "pts_asts":
            all_values = [g.pts_asts for g in game_logs]
        elif stat == "pts_rebs":
            all_values = [g.pts_rebs for g in game_logs]
        elif stat == "rebs_asts":
            all_values = [g.rebs_asts for g in game_logs]
        elif stat == "minutes":
            all_values = [g.minutes for g in game_logs]
        else:
            all_values = [0]

        averages["season"] = sum(all_values) / len(all_values) if all_values else 0.0

    return averages


def get_player_vs_opponent_history(
    player_id: int,
    opponent_abbr: str,
    seasons: int = 2
) -> List[PlayerGameLog]:
    """Get player's historical performance against a specific opponent.

    Args:
        player_id: NBA player ID
        opponent_abbr: Opponent team abbreviation
        seasons: Number of seasons to look back

    Returns:
        List of game logs against this opponent
    """
    all_logs = []

    # Current season
    current_logs = get_player_game_logs(player_id)
    opponent_logs = [log for log in current_logs if log.opponent_abbr == opponent_abbr]
    all_logs.extend(opponent_logs)

    # Previous seasons (if requested)
    if seasons > 1:
        # Parse current season to get previous
        year = int(CURRENT_SEASON.split("-")[0])
        for i in range(1, seasons):
            prev_season = f"{year - i}-{str(year - i + 1)[-2:]}"
            prev_logs = get_player_game_logs(player_id, season=prev_season)
            opponent_logs = [log for log in prev_logs if log.opponent_abbr == opponent_abbr]
            all_logs.extend(opponent_logs)

    return all_logs


def enrich_player_with_stats(player: Player) -> Player:
    """Add season and recent stats to a player object.

    Args:
        player: Basic player info

    Returns:
        Player with stats filled in
    """
    logs = get_player_game_logs(player.id)

    if not logs:
        return player

    # Season averages
    player.games_played = len(logs)
    player.ppg = sum(g.points for g in logs) / len(logs)
    player.rpg = sum(g.rebounds for g in logs) / len(logs)
    player.apg = sum(g.assists for g in logs) / len(logs)
    player.fg3m_pg = sum(g.fg3m for g in logs) / len(logs)
    player.mpg = sum(g.minutes for g in logs) / len(logs)

    # Recent form (last 5)
    recent = logs[:5]
    if recent:
        player.recent_ppg = sum(g.points for g in recent) / len(recent)
        player.recent_rpg = sum(g.rebounds for g in recent) / len(recent)
        player.recent_apg = sum(g.assists for g in recent) / len(recent)
        player.recent_fg3m = sum(g.fg3m for g in recent) / len(recent)
        player.recent_mpg = sum(g.minutes for g in recent) / len(recent)

    # Minutes stability (standard deviation)
    if len(logs) >= 5:
        import statistics
        minutes_list = [g.minutes for g in logs[:10]]
        player.minutes_std = statistics.stdev(minutes_list) if len(minutes_list) > 1 else 0.0

    # Check if starter
    recent_starts = sum(1 for g in logs[:5] if g.started)
    player.is_starter = recent_starts >= 3

    return player

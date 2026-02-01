"""
Constants and mappings for NBA Prop Betting System.
"""
from typing import Dict, List

# Prop type mappings (normalized names)
PROP_TYPES = {
    "points": ["points", "pts", "player_points"],
    "rebounds": ["rebounds", "rebs", "total_rebounds", "player_rebounds"],
    "assists": ["assists", "asts", "player_assists"],
    "threes": ["threes", "3pm", "three_pointers_made", "player_threes"],
    "pts_rebs_asts": ["pra", "pts+rebs+asts", "points_rebounds_assists"],
    "pts_asts": ["pa", "pts+asts", "points_assists"],
    "pts_rebs": ["pr", "pts+rebs", "points_rebounds"],
    "rebs_asts": ["ra", "rebs+asts", "rebounds_assists"],
    "double_double": ["double_double", "dd"],
}

# Stat categories that map to props
STAT_TO_PROP_MAP = {
    "PTS": ["points", "pts_rebs_asts", "pts_asts", "pts_rebs", "double_double"],
    "REB": ["rebounds", "pts_rebs_asts", "pts_rebs", "rebs_asts", "double_double"],
    "AST": ["assists", "pts_rebs_asts", "pts_asts", "rebs_asts", "double_double"],
    "FG3M": ["threes"],
}

# NBA Team IDs (nba_api format)
TEAM_IDS = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}

# Reverse mapping: ID to abbreviation
TEAM_ID_TO_ABBR = {v: k for k, v in TEAM_IDS.items()}

# Team full names
TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}

# Arena locations for travel distance calculation (lat, lon)
TEAM_LOCATIONS = {
    "ATL": (33.7573, -84.3963), "BOS": (42.3662, -71.0621), "BKN": (40.6826, -73.9754),
    "CHA": (35.2251, -80.8392), "CHI": (41.8807, -87.6742), "CLE": (41.4966, -81.6882),
    "DAL": (32.7905, -96.8103), "DEN": (39.7487, -105.0077), "DET": (42.3410, -83.0550),
    "GSW": (37.7680, -122.3877), "HOU": (29.7508, -95.3621), "IND": (39.7640, -86.1555),
    "LAC": (34.0430, -118.2673), "LAL": (34.0430, -118.2673), "MEM": (35.1382, -90.0506),
    "MIA": (25.7814, -80.1870), "MIL": (43.0451, -87.9173), "MIN": (44.9795, -93.2761),
    "NOP": (29.9490, -90.0821), "NYK": (40.7505, -73.9934), "OKC": (35.4634, -97.5151),
    "ORL": (28.5392, -81.3839), "PHI": (39.9012, -75.1720), "PHX": (33.4457, -112.0712),
    "POR": (45.5316, -122.6668), "SAC": (38.5802, -121.4997), "SAS": (29.4270, -98.4375),
    "TOR": (43.6435, -79.3791), "UTA": (40.7683, -111.9011), "WAS": (38.8981, -77.0209),
}

# Edge type constants
class EdgeType:
    INJURY = "injury"
    SCHEME = "scheme"
    PACE = "pace"
    ROLE = "role"
    SCHEDULE = "schedule"
    MATCHUP_HISTORY = "matchup_history"
    TEAM_EVOLUTION = "team_evolution"

# Stat type defense rankings to track
DEFENSE_STAT_CATEGORIES = [
    "opp_pts",      # Points allowed
    "opp_reb",      # Rebounds allowed
    "opp_ast",      # Assists allowed
    "opp_fg3m",     # 3-pointers allowed
    "opp_pts_paint",    # Paint points allowed
    "opp_pts_fb",       # Fast break points allowed
    "opp_pts_2nd_chance",  # Second chance points allowed
]

# Player positions
POSITIONS = ["G", "G-F", "F-G", "F", "F-C", "C-F", "C"]

# Minimum games for reliable sample
MIN_GAMES_FOR_SAMPLE = 5

# Book names for normalization
BOOKS = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "fd": "FanDuel",
    "dk": "DraftKings",
}

# Season year (update each season)
CURRENT_SEASON = "2024-25"
CURRENT_SEASON_TYPE = "Regular Season"

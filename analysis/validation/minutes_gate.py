"""
Minutes gate validation.
Filters out props where player's minutes are not secure.
"""
from typing import Optional
import statistics
import structlog

from config.settings import get_settings
from data.models.schemas import PropAnalysis, PlayerGameLog

logger = structlog.get_logger()
settings = get_settings()


def validate_minutes_security(analysis: PropAnalysis) -> bool:
    """Validate that a player's minutes are secure enough to bet on.

    Criteria:
    1. Average minutes above threshold
    2. Low minutes variance (consistent role)
    3. No recent DNPs or significant minutes drops
    4. Not returning from injury with minutes restriction

    Args:
        analysis: The prop analysis to validate

    Returns:
        True if minutes are secure, False otherwise
    """
    logs = analysis.player_game_logs

    if not logs:
        logger.debug("minutes_gate_failed", reason="no_game_logs",
                    player=analysis.player.name)
        return False

    # Check minimum games
    if len(logs) < settings.min_minutes_last_n:
        logger.debug("minutes_gate_failed", reason="insufficient_games",
                    player=analysis.player.name, games=len(logs))
        return False

    recent_logs = logs[:settings.min_minutes_last_n]

    # Check 1: Average minutes above threshold
    avg_minutes = sum(g.minutes for g in recent_logs) / len(recent_logs)
    if avg_minutes < settings.min_minutes_threshold:
        logger.debug("minutes_gate_failed", reason="low_avg_minutes",
                    player=analysis.player.name, avg=avg_minutes,
                    threshold=settings.min_minutes_threshold)
        return False

    # Check 2: Minutes variance not too high
    minutes_list = [g.minutes for g in recent_logs]
    if len(minutes_list) > 1:
        std_dev = statistics.stdev(minutes_list)
        # High variance (>7 minutes std) suggests unstable role
        if std_dev > 7.0:
            logger.debug("minutes_gate_failed", reason="high_variance",
                        player=analysis.player.name, std_dev=std_dev)
            return False

    # Check 3: No recent DNPs (0 minutes games)
    dnp_count = sum(1 for g in recent_logs if g.minutes == 0)
    if dnp_count > 0:
        logger.debug("minutes_gate_failed", reason="recent_dnp",
                    player=analysis.player.name, dnps=dnp_count)
        return False

    # Check 4: No single game with very low minutes (possible restriction)
    min_minutes = min(g.minutes for g in recent_logs)
    if min_minutes < 15 and avg_minutes > 25:
        # One game way below average could indicate restriction/foul trouble
        logger.debug("minutes_gate_warning", reason="low_min_game",
                    player=analysis.player.name, min_game=min_minutes)
        # Don't fail, but flag it
        analysis.risk_notes.append(
            f"Had {min_minutes:.0f} min game recently (avg {avg_minutes:.1f})"
        )

    # Check 5: Minutes not trending down significantly
    if len(logs) >= 10:
        recent_5 = sum(g.minutes for g in logs[:5]) / 5
        previous_5 = sum(g.minutes for g in logs[5:10]) / 5

        if recent_5 < previous_5 - 5:  # 5+ minute drop
            logger.debug("minutes_gate_warning", reason="minutes_dropping",
                        player=analysis.player.name,
                        recent=recent_5, previous=previous_5)
            analysis.risk_notes.append(
                f"Minutes trending down: {previous_5:.1f} → {recent_5:.1f}"
            )

    return True


def calculate_minutes_security_score(analysis: PropAnalysis) -> float:
    """Calculate a 0-1 score for minutes security.

    Higher score = more secure minutes situation.

    Args:
        analysis: The prop analysis

    Returns:
        Score from 0.0 to 1.0
    """
    logs = analysis.player_game_logs
    if not logs or len(logs) < 3:
        return 0.0

    recent_logs = logs[:min(10, len(logs))]
    score = 0.5  # Start at neutral

    # Factor 1: Average minutes (max +0.2)
    avg_minutes = sum(g.minutes for g in recent_logs) / len(recent_logs)
    if avg_minutes >= 35:
        score += 0.2
    elif avg_minutes >= 30:
        score += 0.15
    elif avg_minutes >= 28:
        score += 0.1
    elif avg_minutes >= settings.min_minutes_threshold:
        score += 0.05
    else:
        score -= 0.1

    # Factor 2: Consistency (max +0.2)
    minutes_list = [g.minutes for g in recent_logs]
    if len(minutes_list) > 1:
        std_dev = statistics.stdev(minutes_list)
        if std_dev < 3:
            score += 0.2  # Very consistent
        elif std_dev < 5:
            score += 0.1
        elif std_dev > 8:
            score -= 0.1

    # Factor 3: Starter status (max +0.1)
    starts = sum(1 for g in recent_logs if g.started)
    start_rate = starts / len(recent_logs)
    if start_rate >= 0.8:
        score += 0.1
    elif start_rate >= 0.5:
        score += 0.05
    elif start_rate == 0:
        score -= 0.05

    # Factor 4: No DNPs (+0.05)
    dnps = sum(1 for g in recent_logs if g.minutes == 0)
    if dnps == 0:
        score += 0.05
    else:
        score -= 0.1 * dnps

    return max(0.0, min(1.0, score))


def check_injury_return_restriction(
    analysis: PropAnalysis,
    injury_status: Optional[str] = None
) -> bool:
    """Check if player might be on minutes restriction from injury return.

    Args:
        analysis: The prop analysis
        injury_status: Player's current injury status if known

    Returns:
        True if potential restriction concern
    """
    logs = analysis.player_game_logs
    if not logs or len(logs) < 3:
        return False

    # Look for minutes pattern that suggests restriction
    # Typically: gradual ramp up over several games

    recent_3 = logs[:3]
    minutes_recent = [g.minutes for g in recent_3]

    # Check if minutes are ramping up (restriction lifting)
    if minutes_recent[0] > minutes_recent[1] > minutes_recent[2]:
        # Each game more minutes than the last
        if minutes_recent[2] < 20:  # Started with restricted minutes
            analysis.risk_notes.append(
                f"Possible minutes ramp: {minutes_recent[2]:.0f} → "
                f"{minutes_recent[1]:.0f} → {minutes_recent[0]:.0f} min"
            )
            return True

    # Check for unusually low recent game vs typical
    if len(logs) >= 10:
        season_avg = sum(g.minutes for g in logs) / len(logs)
        last_game = logs[0].minutes

        if last_game < season_avg - 10:
            analysis.risk_notes.append(
                f"Last game minutes ({last_game:.0f}) well below "
                f"season average ({season_avg:.1f})"
            )
            return True

    return False


def get_blowout_risk(analysis: PropAnalysis) -> str:
    """Assess blowout risk that could reduce 4th quarter minutes.

    Args:
        analysis: The prop analysis

    Returns:
        Risk level: "low", "medium", or "high"
    """
    # This would ideally use Vegas spreads
    game = analysis.game

    # Check if there's a large spread (if available)
    if game.spread:
        if abs(game.spread) >= 12:
            return "high"
        elif abs(game.spread) >= 8:
            return "medium"

    # Check team records/quality difference
    # For now, assume medium risk without spread data
    return "low"

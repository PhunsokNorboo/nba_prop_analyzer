"""
Confidence ranking for prop analyses.
Scores and ranks props to select the top picks.
"""
from typing import List
import structlog

from config.settings import get_settings
from data.models.schemas import PropAnalysis
from analysis.validation.minutes_gate import (
    validate_minutes_security, calculate_minutes_security_score
)

logger = structlog.get_logger()
settings = get_settings()


def rank_props(analyses: List[PropAnalysis]) -> List[PropAnalysis]:
    """Rank prop analyses by confidence and select top picks.

    Scoring factors:
    1. Edge strength (multiple independent edges = higher)
    2. Minutes security
    3. Sample quality (more games, consistent patterns)
    4. Odds value (better odds = bonus)
    5. Historical hit rate

    Args:
        analyses: List of prop analyses

    Returns:
        Sorted list with confidence scores filled in
    """
    # First, validate all props pass minutes gate
    valid_analyses = []
    for analysis in analyses:
        if validate_minutes_security(analysis):
            valid_analyses.append(analysis)
        else:
            logger.debug("filtered_by_minutes_gate", player=analysis.player.name)

    # Score each analysis
    for analysis in valid_analyses:
        analysis.confidence_score = calculate_confidence_score(analysis)
        analysis.minutes_security_score = calculate_minutes_security_score(analysis)

    # Sort by confidence (highest first)
    valid_analyses.sort(key=lambda x: x.confidence_score, reverse=True)

    logger.info(
        "ranked_props",
        total_analyzed=len(analyses),
        passed_validation=len(valid_analyses),
        top_score=valid_analyses[0].confidence_score if valid_analyses else 0
    )

    return valid_analyses


def calculate_confidence_score(analysis: PropAnalysis) -> float:
    """Calculate overall confidence score for a prop.

    Args:
        analysis: The prop analysis

    Returns:
        Confidence score from 0.0 to 1.0
    """
    score = 0.0

    # Factor 1: Edge strength (max 0.35)
    edge_score = _calculate_edge_score(analysis)
    score += edge_score * 0.35

    # Factor 2: Minutes security (max 0.25)
    minutes_score = calculate_minutes_security_score(analysis)
    score += minutes_score * 0.25

    # Factor 3: Sample quality (max 0.15)
    sample_score = _calculate_sample_quality_score(analysis)
    score += sample_score * 0.15

    # Factor 4: Odds value (max 0.15)
    odds_score = _calculate_odds_value_score(analysis)
    score += odds_score * 0.15

    # Factor 5: Hit rate / projection alignment (max 0.10)
    alignment_score = _calculate_alignment_score(analysis)
    score += alignment_score * 0.10

    return min(score, 1.0)


def _calculate_edge_score(analysis: PropAnalysis) -> float:
    """Score based on edge quantity and quality.

    Args:
        analysis: The prop analysis

    Returns:
        Score from 0.0 to 1.0
    """
    edges = analysis.edges
    if not edges:
        return 0.0

    # Average edge strength
    avg_strength = sum(e.strength for e in edges) / len(edges)

    # Bonus for multiple edges
    multi_edge_bonus = min(len(edges) * 0.1, 0.3)

    # Bonus for primary (high-confidence) edges
    primary_edges = [e for e in edges if e.is_primary]
    primary_bonus = len(primary_edges) * 0.05

    score = avg_strength + multi_edge_bonus + primary_bonus
    return min(score, 1.0)


def _calculate_sample_quality_score(analysis: PropAnalysis) -> float:
    """Score based on data quality and sample size.

    Args:
        analysis: The prop analysis

    Returns:
        Score from 0.0 to 1.0
    """
    logs = analysis.player_game_logs

    if not logs:
        return 0.0

    score = 0.0

    # More games = higher score
    if len(logs) >= 30:
        score += 0.4
    elif len(logs) >= 20:
        score += 0.3
    elif len(logs) >= 10:
        score += 0.2
    elif len(logs) >= 5:
        score += 0.1

    # Contextual splits available
    if analysis.conditional_splits:
        score += 0.2

    # H2H history available
    if "vs_opponent" in analysis.conditional_splits:
        h2h = analysis.conditional_splits["vs_opponent"]
        if isinstance(h2h, dict) and h2h.get("games", 0) >= 2:
            score += 0.2

    # Recent form consistent with projection
    if len(logs) >= 5:
        score += 0.2

    return min(score, 1.0)


def _calculate_odds_value_score(analysis: PropAnalysis) -> float:
    """Score based on odds value.

    Better odds (less juice) = higher score.
    Plus money = bonus.

    Args:
        analysis: The prop analysis

    Returns:
        Score from 0.0 to 1.0
    """
    prop = analysis.prop
    direction = analysis.direction

    odds = prop.over_odds if direction == "over" else prop.under_odds

    # Plus money is great
    if odds > 0:
        return 0.8 + min(odds / 500, 0.2)  # Up to +100 = 1.0

    # Standard juice (-110)
    if odds >= -115:
        return 0.7

    # Moderate juice (-120 to -130)
    if odds >= -130:
        return 0.5

    # High juice (-131 to -140)
    if odds >= -140:
        return 0.3

    # Beyond threshold (shouldn't happen after filtering)
    return 0.0


def _calculate_alignment_score(analysis: PropAnalysis) -> float:
    """Score based on projection alignment with line.

    Higher score if projection clearly beats line.

    Args:
        analysis: The prop analysis

    Returns:
        Score from 0.0 to 1.0
    """
    line = analysis.prop.line
    direction = analysis.direction

    if direction == "over":
        # How much does projected mid exceed line?
        edge = analysis.projected_mid - line
        # Also check projected low (floor)
        floor_edge = analysis.projected_low - line
    else:
        # How much is line above projected mid?
        edge = line - analysis.projected_mid
        floor_edge = line - analysis.projected_high

    # Strong edge (mid projection beats line by 2+ units)
    if edge >= 2:
        score = 0.8
    elif edge >= 1:
        score = 0.6
    elif edge >= 0.5:
        score = 0.4
    elif edge > 0:
        score = 0.2
    else:
        score = 0.0

    # Bonus if even the floor/ceiling beats line
    if floor_edge > 0:
        score += 0.2

    return min(score, 1.0)


def select_top_picks(
    analyses: List[PropAnalysis],
    max_picks: int = None
) -> List[PropAnalysis]:
    """Select the top picks from ranked analyses.

    Args:
        analyses: Ranked list of analyses
        max_picks: Maximum number to select

    Returns:
        Top picks (may be fewer than max if not enough quality)
    """
    if max_picks is None:
        max_picks = settings.max_picks

    # Filter to only high-confidence picks
    quality_threshold = 0.4  # Minimum confidence to recommend
    quality_picks = [a for a in analyses if a.confidence_score >= quality_threshold]

    # Take top N
    top_picks = quality_picks[:max_picks]

    logger.info(
        "selected_top_picks",
        total_quality=len(quality_picks),
        selected=len(top_picks)
    )

    return top_picks


def diversify_picks(
    analyses: List[PropAnalysis],
    max_per_player: int = 1,
    max_per_game: int = 2
) -> List[PropAnalysis]:
    """Ensure diversity in picks (not all same player/game).

    Args:
        analyses: Ranked list (already sorted by confidence)
        max_per_player: Max picks for same player
        max_per_game: Max picks from same game

    Returns:
        Diversified list
    """
    selected = []
    player_counts = {}
    game_counts = {}

    for analysis in analyses:
        player = analysis.player.name
        game = analysis.game.id

        # Check limits
        if player_counts.get(player, 0) >= max_per_player:
            continue
        if game_counts.get(game, 0) >= max_per_game:
            continue

        selected.append(analysis)
        player_counts[player] = player_counts.get(player, 0) + 1
        game_counts[game] = game_counts.get(game, 0) + 1

    return selected

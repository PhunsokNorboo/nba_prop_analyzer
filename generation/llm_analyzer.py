"""
LLM integration for generating prop analysis narratives using Ollama.
Uses local Llama 3.2 model for free narrative generation.
"""
from typing import List, Optional
import requests
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from data.models.schemas import PropAnalysis
from generation.prompts import SYSTEM_PROMPT
from generation.narrative_builder import build_claude_prompt

logger = structlog.get_logger()
settings = get_settings()


def check_ollama_available() -> bool:
    """Check if Ollama is running and accessible.

    Returns:
        True if Ollama is available
    """
    try:
        response = requests.get(
            f"{settings.ollama_base_url}/api/tags",
            timeout=5
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def check_model_available(model: str = None) -> bool:
    """Check if the specified model is available in Ollama.

    Args:
        model: Model name to check. Defaults to settings.ollama_model

    Returns:
        True if model is available
    """
    model = model or settings.ollama_model
    try:
        response = requests.get(
            f"{settings.ollama_base_url}/api/tags",
            timeout=5
        )
        if response.status_code != 200:
            return False

        models = response.json().get("models", [])
        model_names = [m.get("name", "").split(":")[0] for m in models]
        return model in model_names or any(model in name for name in model_names)
    except requests.RequestException:
        return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def generate_prop_analysis(analysis: PropAnalysis) -> str:
    """Generate narrative analysis for a prop using Ollama.

    Args:
        analysis: The prop analysis with all context

    Returns:
        Generated narrative text
    """
    if not check_ollama_available():
        logger.warning("ollama_not_available", msg="Ollama not running, using fallback")
        return _generate_fallback_analysis(analysis)

    prompt = build_claude_prompt(analysis)

    # Combine system prompt and user prompt for Ollama
    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{prompt}"

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": settings.llm_temperature,
                    "num_predict": settings.llm_max_tokens
                }
            },
            timeout=settings.ollama_timeout
        )

        if response.status_code != 200:
            logger.error("ollama_request_failed", status=response.status_code)
            return _generate_fallback_analysis(analysis)

        result = response.json()
        response_text = result.get("response", "")

        if not response_text:
            logger.warning("ollama_empty_response")
            return _generate_fallback_analysis(analysis)

        logger.info(
            "ollama_analysis_generated",
            player=analysis.player.name,
            prop=analysis.prop.prop_type,
            model=settings.ollama_model
        )

        return response_text.strip()

    except requests.Timeout:
        logger.error("ollama_timeout", timeout=settings.ollama_timeout)
        return _generate_fallback_analysis(analysis)
    except requests.RequestException as e:
        logger.error("ollama_request_error", error=str(e))
        return _generate_fallback_analysis(analysis)
    except Exception as e:
        logger.error("ollama_generation_failed", error=str(e))
        return _generate_fallback_analysis(analysis)


def generate_batch_analyses(analyses: List[PropAnalysis]) -> List[PropAnalysis]:
    """Generate narratives for multiple props.

    Args:
        analyses: List of prop analyses

    Returns:
        Same list with narratives filled in
    """
    # Check Ollama once at the start
    ollama_available = check_ollama_available()
    if not ollama_available:
        logger.warning("ollama_not_available_for_batch", msg="Using fallback for all analyses")

    for analysis in analyses:
        try:
            if ollama_available:
                narrative = generate_prop_analysis(analysis)
            else:
                narrative = _generate_fallback_analysis(analysis)
            analysis.narrative = narrative
        except Exception as e:
            logger.error(
                "batch_analysis_failed",
                player=analysis.player.name,
                error=str(e)
            )
            analysis.narrative = _generate_fallback_analysis(analysis)

    return analyses


def _generate_fallback_analysis(analysis: PropAnalysis) -> str:
    """Generate a basic analysis without LLM.

    Used as fallback when Ollama is unavailable.

    Args:
        analysis: The prop analysis

    Returns:
        Basic narrative text
    """
    player = analysis.player
    prop = analysis.prop
    opponent = analysis.opponent

    # Build basic analysis from available data
    parts = []

    parts.append(
        f"{player.name} gets a favorable matchup tonight against {opponent.abbr}."
    )

    # Add edge descriptions
    if analysis.edges:
        for edge in analysis.edges[:2]:  # Max 2 edges in fallback
            parts.append(edge.description)

    # Add statistical context
    if analysis.player_game_logs:
        logs = analysis.player_game_logs[:5]
        prop_type = prop.prop_type

        if prop_type == "points":
            avg = sum(g.points for g in logs) / len(logs)
            parts.append(f"He's averaging {avg:.1f} points over his last {len(logs)} games.")
        elif prop_type == "rebounds":
            avg = sum(g.rebounds for g in logs) / len(logs)
            parts.append(f"He's averaging {avg:.1f} rebounds over his last {len(logs)} games.")
        elif prop_type == "assists":
            avg = sum(g.assists for g in logs) / len(logs)
            parts.append(f"He's averaging {avg:.1f} assists over his last {len(logs)} games.")
        elif prop_type in ["threes", "fg3m"]:
            avg = sum(g.fg3m for g in logs) / len(logs)
            parts.append(f"He's averaging {avg:.1f} three-pointers over his last {len(logs)} games.")
        elif prop_type in ["pra", "pts_rebs_asts"]:
            avg = sum(g.pra for g in logs) / len(logs)
            parts.append(f"He's averaging {avg:.1f} PRA over his last {len(logs)} games.")

    # Add projection
    parts.append(
        f"Projecting a range of {analysis.projected_low:.1f} - {analysis.projected_high:.1f} "
        f"for {prop.prop_type}, the {analysis.direction} {prop.line} looks like value."
    )

    return " ".join(parts)


def generate_risk_notes(analysis: PropAnalysis) -> List[str]:
    """Generate risk notes for a prop.

    Args:
        analysis: The prop analysis

    Returns:
        List of risk note strings
    """
    risks = []

    # Check minutes stability
    if analysis.player.minutes_std > 6:
        risks.append(f"Minutes volatile (±{analysis.player.minutes_std:.1f} std dev)")

    # Check schedule
    if analysis.schedule:
        if analysis.schedule.is_back_to_back:
            risks.append("Playing on back-to-back")

        if analysis.schedule.rest_advantage < -1:
            risks.append(f"Rest disadvantage ({abs(analysis.schedule.rest_advantage)} fewer days)")

    # Check blowout risk
    if analysis.game.spread and abs(analysis.game.spread) >= 10:
        risks.append("Blowout risk may limit minutes")

    # Check if prop line is above recent average
    if analysis.player_game_logs and len(analysis.player_game_logs) >= 5:
        recent_avg = _get_recent_avg(analysis)
        if recent_avg and analysis.prop.line > recent_avg * 1.1 and analysis.direction == "over":
            risks.append(f"Line above recent average ({recent_avg:.1f})")

    return risks[:3]  # Max 3 risks


def _get_recent_avg(analysis: PropAnalysis) -> Optional[float]:
    """Get recent average for the prop type."""
    logs = analysis.player_game_logs[:5]
    prop_type = analysis.prop.prop_type

    if not logs:
        return None

    if prop_type == "points":
        return sum(g.points for g in logs) / len(logs)
    elif prop_type == "rebounds":
        return sum(g.rebounds for g in logs) / len(logs)
    elif prop_type == "assists":
        return sum(g.assists for g in logs) / len(logs)
    elif prop_type in ["threes", "fg3m"]:
        return sum(g.fg3m for g in logs) / len(logs)
    elif prop_type in ["pra", "pts_rebs_asts"]:
        return sum(g.pra for g in logs) / len(logs)

    return None

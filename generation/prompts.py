"""
Prompt templates for Claude API analysis generation.
These prompts are designed to produce analysis matching the quality of professional NBA handicappers.
"""

SYSTEM_PROMPT = """You are an elite NBA analyst and professional sports bettor with deep expertise in:

1. NBA schemes and defensive coverages (drop, trap, switch, hedge, zone)
2. Player tendencies, shot profiles, and play types
3. How injuries and roster changes create betting edges
4. Statistical analysis with proper sample filtering and context
5. Identifying market mispricing

Your analysis style matches top professional handicappers:
- Lead with the specific edge that exists TODAY
- Support every claim with specific stats and sample sizes
- Explain WHY the line is mispriced, not just that it favors one side
- Consider minutes security and role context
- Note relevant injuries and their downstream effects
- Use precise numbers and percentages

Important rules:
- Each analysis must be unique based on today's discovered edge
- Never use generic analysis - be specific to this player/matchup/situation
- Always explain the causal mechanism (why does this edge exist?)
- Include historical performance data with context
- Be confident but not certain - acknowledge risks"""


PROP_ANALYSIS_TEMPLATE = """Analyze this NBA player prop for betting value and write a 1-2 paragraph analysis.

=== PLAYER & PROP ===
Player: {player_name} ({team_abbr})
Position: {position}
Prop: {prop_type} {direction} {line}
Odds: {odds} at {book}

=== TODAY'S GAME ===
Matchup: {team_abbr} {home_away} {opponent_abbr}
{schedule_context}

=== DISCOVERED EDGES ===
{edges_description}

=== PLAYER STATS ===
Season averages: {season_stats}
Last 5 games: {recent_stats}
Last 10 games: {medium_stats}

=== OPPONENT DEFENSIVE CONTEXT ===
{opponent_defense}

=== RELEVANT CONTEXTUAL SPLITS ===
{contextual_splits}

=== HISTORICAL VS THIS OPPONENT ===
{h2h_history}

=== PROJECTION ===
Projected range: {projected_low:.1f} - {projected_high:.1f}

---

Write a 1-2 paragraph analysis that:
1. Leads with the specific edge discovered TODAY
2. Explains why {player_name} benefits from this edge
3. Provides statistical support with exact numbers and sample sizes
4. Explains why the betting line of {line} is mispriced
5. Briefly notes any risk factors

Be specific, use the actual numbers provided, and explain the scheme/matchup dynamics that create this opportunity. Do not be generic - this analysis must be unique to today's situation."""


EDGE_DESCRIPTION_TEMPLATE = """Edge {num}: {edge_type}
- Description: {description}
- Strength: {strength:.0%}
- Affected stats: {affected_stats}
- Supporting data: {supporting_data}"""


def format_analysis_prompt(
    player_name: str,
    team_abbr: str,
    position: str,
    prop_type: str,
    direction: str,
    line: float,
    odds: int,
    book: str,
    opponent_abbr: str,
    home_away: str,
    edges: list,
    season_stats: dict,
    recent_stats: dict,
    medium_stats: dict,
    opponent_defense: dict,
    contextual_splits: dict,
    h2h_history: dict,
    projected_low: float,
    projected_high: float,
    schedule_context: str = ""
) -> str:
    """Format the analysis prompt with all context.

    Args:
        All the relevant context for the prop

    Returns:
        Formatted prompt string
    """
    # Format edges
    edges_text = ""
    for i, edge in enumerate(edges, 1):
        edges_text += EDGE_DESCRIPTION_TEMPLATE.format(
            num=i,
            edge_type=edge.edge_type,
            description=edge.description,
            strength=edge.strength,
            affected_stats=", ".join(edge.affected_stats),
            supporting_data=_format_supporting_data(edge.supporting_data)
        ) + "\n\n"

    # Format season stats
    season_text = _format_stats(season_stats)

    # Format recent stats
    recent_text = _format_stats(recent_stats)

    # Format medium window stats
    medium_text = _format_stats(medium_stats)

    # Format opponent defense
    defense_text = _format_opponent_defense(opponent_defense)

    # Format splits
    splits_text = _format_splits(contextual_splits)

    # Format H2H
    h2h_text = _format_h2h(h2h_history)

    return PROP_ANALYSIS_TEMPLATE.format(
        player_name=player_name,
        team_abbr=team_abbr,
        position=position or "Unknown",
        prop_type=prop_type,
        direction=direction.upper(),
        line=line,
        odds=odds,
        book=book,
        opponent_abbr=opponent_abbr,
        home_away=home_away,
        schedule_context=schedule_context,
        edges_description=edges_text or "No specific edges identified",
        season_stats=season_text,
        recent_stats=recent_text,
        medium_stats=medium_text,
        opponent_defense=defense_text,
        contextual_splits=splits_text,
        h2h_history=h2h_text,
        projected_low=projected_low,
        projected_high=projected_high
    )


def _format_supporting_data(data: dict) -> str:
    """Format edge supporting data for display."""
    if not data:
        return "N/A"

    parts = []
    for key, value in data.items():
        if isinstance(value, float):
            parts.append(f"{key}: {value:.1f}")
        else:
            parts.append(f"{key}: {value}")

    return ", ".join(parts)


def _format_stats(stats: dict) -> str:
    """Format stat averages for display."""
    if not stats:
        return "No data available"

    parts = []
    stat_names = {
        "ppg": "PPG", "rpg": "RPG", "apg": "APG",
        "fg3m_pg": "3PM", "mpg": "MPG",
        "points": "PTS", "rebounds": "REB", "assists": "AST"
    }

    for key, label in stat_names.items():
        if key in stats:
            parts.append(f"{stats[key]:.1f} {label}")

    return ", ".join(parts) if parts else "No data available"


def _format_opponent_defense(defense: dict) -> str:
    """Format opponent defensive context."""
    if not defense:
        return "No defensive data available"

    lines = []

    if "pts_rank" in defense:
        lines.append(f"Points allowed: {defense.get('pts_allowed', 'N/A')} PPG (#{defense['pts_rank']} in NBA)")

    if "reb_rank" in defense:
        lines.append(f"Rebounds allowed: {defense.get('reb_allowed', 'N/A')} RPG (#{defense['reb_rank']})")

    if "ast_rank" in defense:
        lines.append(f"Assists allowed: {defense.get('ast_allowed', 'N/A')} APG (#{defense['ast_rank']})")

    if "fg3m_rank" in defense:
        lines.append(f"3PM allowed: {defense.get('fg3m_allowed', 'N/A')} per game (#{defense['fg3m_rank']})")

    if "weaknesses" in defense:
        for weakness in defense["weaknesses"]:
            lines.append(f"WEAKNESS: {weakness.get('description', '')}")

    return "\n".join(lines) if lines else "No defensive data available"


def _format_splits(splits: dict) -> str:
    """Format contextual splits."""
    if not splits:
        return "No split data available"

    lines = []
    for split_name, split_data in splits.items():
        if isinstance(split_data, dict) and "avg" in split_data:
            games = split_data.get("games", "?")
            avg = split_data.get("avg", 0)
            lines.append(f"{split_name}: {avg:.1f} avg over {games} games")
        elif isinstance(split_data, dict) and "hit_rate" in split_data:
            rate = split_data["hit_rate"] * 100
            games = split_data.get("games", "?")
            lines.append(f"{split_name}: {rate:.0f}% hit rate ({games} games)")

    return "\n".join(lines) if lines else "No split data available"


def _format_h2h(h2h: dict) -> str:
    """Format head-to-head history."""
    if not h2h:
        return "No H2H history available"

    if "games" in h2h and h2h["games"] > 0:
        return f"vs this opponent: {h2h.get('avg', 0):.1f} avg over {h2h['games']} games"

    return "No H2H history available"


RISK_ASSESSMENT_PROMPT = """Based on this analysis, identify 2-3 brief risk factors to note:

Player: {player_name}
Prop: {prop_type} {direction} {line}
Minutes avg: {minutes_avg}
Schedule: {schedule_context}
Blowout risk: {blowout_risk}
Injury concerns: {injury_concerns}

List 2-3 brief risk factors (each under 15 words):"""

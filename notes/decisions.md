# Architecture Decisions

> Document key technical decisions and the reasoning behind them.

## 2026-02-01 - Initial Architecture

### Decision: Use Ollama Instead of Anthropic API for Narratives

**Context**: Need LLM to generate prop analysis narratives. Options were:
1. Anthropic Claude API (paid, higher quality)
2. Local Ollama with Llama 3.2 (free, good enough)

**Decision**: Use Ollama/Llama 3.2 for narrative generation.

**Rationale**:
- Cost: Free vs ~$0.50-1.00/day
- Quality: Llama 3.2 is sufficient for writing analysis
- Future: Can add Anthropic for edge discovery later (analysis needs higher capability than writing)

**Consequences**:
- Must have Ollama running locally (`ollama serve`)
- Must have model pulled (`ollama pull llama3.2`)
- Fallback template if Ollama unavailable

---

### Decision: Dynamic Edge Discovery Over Templates

**Context**: How to identify betting edges each day?

**Decision**: Build an edge discovery engine that scans all available data and identifies anomalies, rather than using fixed templates.

**Rationale**:
- Markets change daily - what's an edge today may not be tomorrow
- Templates force-fit patterns that may not exist
- Dynamic discovery finds edges we didn't anticipate

**Consequences**:
- More complex code
- Requires comprehensive data collection
- May find 0 plays on some days (feature, not bug)

---

### Decision: Minutes Gate as Primary Validator

**Context**: How to avoid volatile player props?

**Decision**: Implement strict minutes gate:
- Minimum 24 MPG over last 5 games
- Standard deviation < 7 minutes
- No DNPs in last 5

**Rationale**:
- Minutes drive stats - unstable minutes = unstable props
- Steals/blocks already excluded for volatility
- Minutes variance catches role uncertainty

**Consequences**:
- Will filter out some real opportunities
- Prioritizes safety over upside
- May need tuning based on results

---

### Decision: Cache TTLs by Data Type

**Context**: How often to refresh different data types?

**Decision**:
- Stats: 4 hours (don't change during day)
- Props: 30 minutes (lines move)
- Injuries: 1 hour (can change)
- Schedule: 24 hours (static)

**Rationale**:
- Balance freshness vs API limits
- Props are most time-sensitive
- nba_api has rate limits (0.6s between calls)

**Consequences**:
- May miss very fast line moves
- Adequate for daily analysis at 10 AM

---

*Add new decisions as they are made*

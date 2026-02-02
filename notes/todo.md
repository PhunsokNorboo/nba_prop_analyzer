# Future Enhancements

> Track planned improvements and feature ideas.

## URGENT

### Fix Defensive Rankings Data
- **Status**: BROKEN
- **Problem**: Using PLUS_MINUS as proxy gives wrong rankings (DET showed 18th, actually 4th)
- **Impact**: Picking OVER against elite defenses thinking they're bad
- **Fix options**:
  1. Use nba_api `leaguedashteamstats` with `measure_type="Opponent"`
  2. Scrape ESPN defensive stats page
  3. Use different endpoint for true opponent PPG
- **Priority**: Must fix before next run

---

## High Priority

### Add Claude API Integration (Tiered)
- **Status**: Planned
- **Description**: Add Claude API as optional LLM backend with tier selection
- **Tiers**:
  - `free` - Ollama only (current)
  - `budget` - Haiku (~$1.50/month)
  - `standard` - Sonnet (~$9/month)
  - `premium` - Opus 4.5 (~$90/month)
- **Hybrid approach**: Use Opus for edge discovery, Haiku for narratives (~$50/month)
- **Implementation**:
  - Add `ANTHROPIC_API_KEY` to settings
  - Add `LLM_TIER` setting (free/budget/standard/premium)
  - Create `generation/claude_client.py` for API calls
  - Keep Ollama as fallback
- **Dependency**: User opts in when ready

### Implement Backtesting Framework
- **Status**: Planned
- **Description**: Run system on historical data to validate edge detection
- **Rationale**: Need to verify edges actually hit before trusting live
- **Approach**: Store daily picks, compare to actual results

## Medium Priority

### Add Play-Type Data from nba_api Tracking
- **Status**: Planned
- **Description**: Incorporate tracking data for shot types, play types
- **Rationale**: More granular edge discovery (e.g., "scores 24% in transition")
- **Dependency**: nba_api tracking endpoints

### Referee Tendency Analysis
- **Status**: Idea
- **Description**: Track ref assignments and their impact on game flow
- **Rationale**: Some refs call more fouls, affecting pace/minutes
- **Dependency**: Find reliable ref assignment data source

### Slack Delivery Option
- **Status**: Idea
- **Description**: Send picks to Slack in addition to email
- **Rationale**: More immediate notification
- **Dependency**: Slack webhook setup

## Low Priority / Nice to Have

### Web Dashboard
- **Status**: Idea
- **Description**: Build simple web UI to view picks and historical performance
- **Rationale**: Better UX than email
- **Dependency**: Time investment

### Multi-Sport Expansion
- **Status**: Future
- **Description**: Apply same framework to NFL, MLB
- **Rationale**: Same principles apply
- **Dependency**: Complete NBA system first

### Line Shopping Integration
- **Status**: Idea
- **Description**: Automatically find best odds across all books
- **Rationale**: Better odds = better edge
- **Dependency**: More sportsbook APIs

---

## Completed

### Switch from Anthropic to Ollama - DONE 2026-02-01
- Replaced Claude API with local Llama 3.2
- Added fallback template generation
- Updated all imports and settings

### Create Project CLAUDE.md - DONE 2026-02-01
- Project-specific rules documented
- Session logging established
- Notes directory created

---

*Update this list as features are completed or new ideas emerge*

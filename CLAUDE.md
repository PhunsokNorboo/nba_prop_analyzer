# NBA Prop Betting System - Project Rules

> This file contains project-specific rules and learnings. Update after every session.
> See `notes/` directory for detailed decisions and task history.

## Data Collection Rules

### nba_api
- **Rate limit**: 0.6 seconds between API calls (will get IP blocked otherwise)
- **Empty DataFrames**: Always check `if df.empty` before processing
- **Season format**: Use "2024-25" format, not "2024-2025"
- **Player IDs**: Use `players.get_players()` for lookups, not hardcoded IDs

### Caching TTLs
- Stats: 4 hours (14400 seconds)
- Props: 30 minutes (1800 seconds) - lines move fast
- Injuries: 1 hour (3600 seconds)
- Schedule: 24 hours (86400 seconds)

### Props Scraping
- The Odds API free tier: 500 requests/month - use caching aggressively
- Normalize player names between sources (different spellings)
- Always filter to allowed prop types BEFORE processing
- **Props timing window**: Props get pulled ~30 mins before tip-off, and may not be posted until ~2-3 hours before
- **Best run time**: 2-4 hours before first game of the day for maximum prop coverage

## Edge Discovery Rules

### Edge Strength Thresholds
- Minimum strength to consider: 0.5
- Injury edge from star (25+ usage): 0.6-0.8 strength
- Scheme weakness (bottom 10 defense): 0.5-0.7 strength
- Multiple independent edges = compound the confidence

### Injury Edges
- Only OUT and DOUBTFUL create edges (not Questionable/Probable)
- Track usage rate and minutes of injured player
- Check BOTH teammate opportunity AND opponent opportunity

### What Creates an Edge
- Key player injury (15+ usage or 25+ minutes)
- Defensive ranking bottom 10 in a stat category
- Back-to-back with rest disadvantage >= 2 days
- Player role change (3+ minute increase recently)
- Historical dominance vs specific opponent

### What Does NOT Create an Edge
- Season-long averages alone
- "Good player vs bad team" without specifics
- Speculative lineup changes
- Questionable/Probable injury status

## Validation Rules

### Minutes Gate (NON-NEGOTIABLE)
- Minimum 24 MPG average over last 5 games
- Standard deviation < 7 minutes (stable role)
- No DNPs in last 5 games
- Must be in rotation (not coach's doghouse)

### Hard Filters
- **Odds**: Never worse than -140
- **Prop types**: Only points, rebounds, assists, threes, combos
- **EXCLUDE**: Steals, blocks, turnovers (too volatile)

### Sample Quality
- Minimum 5 games for any split
- H2H history: 2+ games is meaningful
- "Since X happened" samples > full season if inflection point exists

## LLM Rules (Ollama/Llama 3.2)

### Generation
- Model: `llama3.2` (local, free)
- Timeout: 120 seconds
- Temperature: 0.7 (slightly creative for natural writing)
- Always have fallback template if Ollama unavailable

### Prompts
- Include specific numbers in context (not "good" or "high")
- State the edge explicitly in the prompt
- Ask for 1-2 paragraphs, not more
- Request scheme-level insight, not generic analysis

## Output Rules

### Pick Selection
- Maximum 4 picks per day
- Diversify: max 1 prop per player, max 2 per game
- Quality over quantity: 0 picks is valid if no edges exist

### Format
- Always include: Player, Prop, Direction, Line, Book, Odds, Projection
- Risk notes: Max 3 bullet points
- Analysis: 1-2 paragraphs, leads with the edge

## Common Pitfalls (Add to this list)

1. **Don't trust season averages blindly** - Check for inflection points
2. **Don't mix pre/post injury samples** - Filter to consistent context
3. **Minutes can change quickly** - Always check last 5, not just season
4. **Props move** - Cache for 30 min max, line you saw may be gone
5. **Rate limits are real** - nba_api will block you without delays
6. **Verify projections vs actual averages** - If line ≈ season avg, there's no edge (Cam Thomas 2/1: projected 18-28, actual avg 16, line 15.5 = no real edge)

## Future Enhancements (Tracked)

- [ ] Add Anthropic API for AI-powered edge discovery
- [ ] Implement play-type data from nba_api tracking
- [ ] Add referee tendency analysis
- [ ] Build backtesting framework
- [ ] Add Slack delivery option

---

## Session Log

### 2026-02-01 - Initial Build
- Created full system with 36 Python files
- Switched from Anthropic to Ollama for cost savings
- Set up project CLAUDE.md and notes directory

### 2026-02-01 - First Test Run & Fixes
- **nba_api endpoint change**: `scoreboard` → `scoreboardv2.ScoreboardV2`
- **Props don't have team_abbr**: Must look up player teams from `get_league_player_stats()`
- **Props don't have player_id**: Must look up from `nba_api.stats.static.players`
- **Defensive rankings broken**: Fixed ranking calculation using PLUS_MINUS as proxy
- **Edge threshold too strict**: Relaxed from rank >= 21 to >= 16 for more coverage
- **Odds API partial coverage**: Not all games have props (some already started)
- **EMAIL_ENABLED setting added**: Can run console-only without email credentials
- First successful run: 2 picks generated with full analysis

*Update this section after each work session*

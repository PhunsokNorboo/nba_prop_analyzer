# Learnings

> Document discoveries, gotchas, and insights from development and operation.

## 2026-02-01 - Initial Development

### nba_api Quirks

1. **Rate Limiting is Strict**
   - Must wait 0.6 seconds between API calls
   - Getting blocked means waiting 10+ minutes
   - Always use the rate-limited wrapper functions

2. **Season Format**
   - Use "2024-25" NOT "2024-2025"
   - This trips up many first-time users

3. **Empty DataFrames**
   - Many endpoints return empty DataFrames instead of errors
   - Always check `if df.empty` before processing
   - Don't assume data exists

4. **Player IDs**
   - Use `players.get_players()` for lookups
   - Don't hardcode IDs - they're not intuitive
   - Name matching can be tricky (Jr., III, etc.)

### Ollama Integration

1. **Check Availability First**
   - Ollama may not be running
   - Always have fallback template ready
   - Don't let LLM failure break the pipeline

2. **Timeout Settings**
   - 120 seconds is reasonable for Llama 3.2
   - Shorter timeouts cause unnecessary failures
   - Local generation is slower than API

### Edge Discovery

1. **Not All Injuries Matter**
   - Only OUT and DOUBTFUL create real edges
   - Questionable/Probable players usually play
   - Check usage rate - low usage injuries don't matter

2. **Opponent vs Teammate Edges**
   - When star is out, check BOTH:
     - Opponent opportunity (facing weaker team)
     - Teammate opportunity (more shots/usage)
   - Both can be valuable

### Props Data

1. **Lines Move Fast**
   - 30 minute cache is maximum
   - Best lines go quickly
   - Line you saw may not be available

2. **Book Differences**
   - Same prop can have different odds across books
   - Always note which book has the line
   - -140 on one book might be -115 on another

---

*Add new learnings as they are discovered*

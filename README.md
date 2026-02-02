# NBA Prop Analyzer

Automated NBA player prop analysis system that discovers statistical edges and generates betting recommendations.

## How It Works

```
Games → Props → Edge Discovery → Validation → Analysis → Picks
```

1. **Fetches today's games** from NBA API
2. **Collects player props** from FanDuel/DraftKings via The Odds API
3. **Discovers edges** based on:
   - Defensive matchups (team rankings by stat type)
   - Injury impacts (teammate/opponent opportunities)
   - Schedule factors (rest, back-to-backs)
   - Role changes (minutes/usage trends)
4. **Validates picks** through minutes gate (stable role, 24+ MPG)
5. **Generates analysis** using local LLM (Ollama/Llama 3.2)
6. **Outputs top 4 picks** with projections and risk notes

## Sample Output

```
PICK #1
----------------------------------------
Cam Thomas - Points - OVER 15.5
Book: FanDuel
Odds: -102
Projected Range: 18.1 - 28.4

[Analysis explaining the edge, matchup dynamics,
and why the line is mispriced...]

Risk Notes: Standard risks apply
```

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/PhunsokNorboo/nba_prop_analyzer.git
cd nba_prop_analyzer
pip install -r requirements.txt
```

### 2. Get API Key

Sign up for free at [The Odds API](https://the-odds-api.com) (500 requests/month free)

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your ODDS_API_KEY
```

### 4. Start Ollama

```bash
ollama serve
ollama pull llama3.2
```

### 5. Run

```bash
python main.py
```

## Configuration

Key settings in `.env`:

| Setting | Default | Description |
|---------|---------|-------------|
| `ODDS_API_KEY` | - | Required for prop lines |
| `MIN_ODDS` | -140 | Filter out heavy juice |
| `MAX_PICKS` | 4 | Daily pick limit |
| `MIN_MINUTES_THRESHOLD` | 24 | Minutes gate filter |
| `EMAIL_ENABLED` | false | Enable email delivery |

## Project Structure

```
├── analysis/
│   ├── edge_discovery/    # Injury, scheme, pace, role edges
│   ├── validation/        # Minutes gate, sample filters
│   └── matchup_engine.py  # Maps edges to props
├── data/
│   ├── collectors/        # NBA API, Odds API, injuries
│   └── models/            # Data schemas
├── generation/
│   └── llm_analyzer.py    # Ollama integration
├── output/
│   ├── ranker.py          # Confidence scoring
│   └── formatter.py       # Pick formatting
├── delivery/
│   ├── email_sender.py    # SMTP delivery
│   └── scheduler.py       # Daily automation
└── main.py                # Entry point
```

## Prop Types Supported

- Points
- Rebounds
- Assists
- Three-Pointers Made
- Combos (PRA, P+A, P+R, R+A)

**Excluded**: Steals, blocks, turnovers (too volatile)

## Automation

Run daily at 10 AM ET:

```bash
python main.py --schedule
```

Or set up a cron job for hands-free operation.

## Limitations

- Props availability depends on timing (2-4 hours before tip-off is optimal)
- LLM narratives may embellish stats (picks are based on real data)
- Free Odds API tier: 500 requests/month
- NBA API rate limited: 0.6s between calls

## Tech Stack

- **Data**: nba_api, The Odds API
- **LLM**: Ollama (Llama 3.2)
- **Framework**: Python, Pandas
- **Scheduling**: APScheduler

## License

MIT

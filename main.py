"""
NBA Player Prop Betting Analysis System - Main Entry Point

This is the main orchestrator that runs the daily analysis pipeline:
1. Fetch today's games
2. Collect data (stats, props, injuries, schedule)
3. Discover edges
4. Match edges to props
5. Validate props (minutes gate, sample quality)
6. Generate LLM analysis for top candidates (Ollama/Llama 3.2)
7. Rank and select top 4 picks
8. Format and deliver via email

Usage:
    python main.py              # Run analysis now
    python main.py --schedule   # Start scheduler for daily runs
"""
import argparse
import sys
from datetime import datetime, date
from pathlib import Path
import structlog

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import get_settings
from data.collectors.nba_stats import get_todays_games
from data.collectors.props_scraper import get_all_props_for_games, filter_props_by_odds, filter_props_by_type
from data.collectors.injury_tracker import get_injury_report
from data.collectors.schedule import get_all_schedule_contexts, identify_schedule_edges
from analysis.edge_discovery.injury_edges import find_injury_edges
from analysis.edge_discovery.scheme_edges import find_scheme_edges, find_pace_edges
from analysis.edge_discovery.role_edges import find_role_edges
from analysis.matchup_engine import match_edges_to_props, enrich_analysis_with_context
from analysis.validation.minutes_gate import validate_minutes_security
from generation.llm_analyzer import generate_batch_analyses, generate_risk_notes
from output.ranker import rank_props, select_top_picks, diversify_picks
from output.formatter import format_pick, format_picks_text, format_picks_html
from delivery.email_sender import send_email_report, send_error_notification, send_no_picks_notification

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()
settings = get_settings()


def run_analysis():
    """Main analysis pipeline.

    Returns:
        List of FormattedPick objects, or empty list if no picks
    """
    logger.info("analysis_started", timestamp=datetime.now().isoformat())

    try:
        # Step 1: Get today's games
        logger.info("step_1_fetching_games")
        games = get_todays_games()

        if not games:
            logger.info("no_games_today")
            if settings.email_enabled:
                send_no_picks_notification("No NBA games scheduled today")
            print("No NBA games scheduled today")
            return []

        logger.info("games_found", count=len(games))

        # Step 2: Collect props
        logger.info("step_2_fetching_props")
        props = get_all_props_for_games(games)

        if not props:
            logger.warning("no_props_available")
            if settings.email_enabled:
                send_no_picks_notification("Could not fetch prop lines from sportsbooks")
            print("Could not fetch prop lines from sportsbooks")
            return []

        # Filter by odds and allowed types
        props = filter_props_by_odds(props, settings.min_odds)
        props = filter_props_by_type(props, settings.allowed_prop_types)

        logger.info("props_filtered", count=len(props))

        if not props:
            logger.warning("no_props_after_filtering")
            if settings.email_enabled:
                send_no_picks_notification("No props met odds/type criteria")
            print("No props met odds/type criteria")
            return []

        # Step 3: Discover edges
        logger.info("step_3_discovering_edges")
        all_edges = []

        # Injury edges
        injury_edges = find_injury_edges(games)
        all_edges.extend(injury_edges)
        logger.info("injury_edges_found", count=len(injury_edges))

        # Scheme/defense edges
        scheme_edges = find_scheme_edges(games)
        all_edges.extend(scheme_edges)
        logger.info("scheme_edges_found", count=len(scheme_edges))

        # Pace edges
        pace_edges = find_pace_edges(games)
        all_edges.extend(pace_edges)
        logger.info("pace_edges_found", count=len(pace_edges))

        # Schedule edges
        schedule_edge_dicts = identify_schedule_edges(games)
        # Convert to Edge objects (simplified for now)
        logger.info("schedule_edges_found", count=len(schedule_edge_dicts))

        if not all_edges:
            logger.warning("no_edges_discovered")
            if settings.email_enabled:
                send_no_picks_notification("No clear edges identified in today's matchups")
            print("No clear edges identified in today's matchups")
            return []

        # Step 4: Match edges to props
        logger.info("step_4_matching_props_to_edges")
        prop_analyses = match_edges_to_props(all_edges, props, games)

        if not prop_analyses:
            logger.warning("no_props_matched")
            if settings.email_enabled:
                send_no_picks_notification("No props aligned with discovered edges")
            print("No props aligned with discovered edges")
            return []

        logger.info("props_matched", count=len(prop_analyses))

        # Step 5: Enrich with context
        logger.info("step_5_enriching_context")
        for analysis in prop_analyses:
            analysis = enrich_analysis_with_context(analysis)

        # Step 6: Validate and rank
        logger.info("step_6_ranking_props")
        ranked_analyses = rank_props(prop_analyses)

        if not ranked_analyses:
            logger.warning("no_props_passed_validation")
            if settings.email_enabled:
                send_no_picks_notification("No props passed validation (minutes/sample quality)")
            print("No props passed validation (minutes/sample quality)")
            return []

        # Diversify picks
        diversified = diversify_picks(ranked_analyses)

        # Select top picks
        top_analyses = select_top_picks(diversified, settings.max_picks)

        logger.info("top_picks_selected", count=len(top_analyses))

        # Step 7: Generate Claude analysis
        logger.info("step_7_generating_analysis")
        top_analyses = generate_batch_analyses(top_analyses)

        # Generate risk notes
        for analysis in top_analyses:
            if not analysis.risk_notes:
                analysis.risk_notes = generate_risk_notes(analysis)

        # Step 8: Format picks
        logger.info("step_8_formatting_output")
        formatted_picks = [
            format_pick(analysis, rank=i+1)
            for i, analysis in enumerate(top_analyses)
        ]

        # Step 9: Deliver
        logger.info("step_9_delivering_picks")
        if formatted_picks:
            if settings.email_enabled:
                success = send_email_report(formatted_picks)
                if success:
                    logger.info("email_delivered", picks=len(formatted_picks))
                else:
                    logger.error("email_delivery_failed")
            else:
                logger.info("email_disabled_skipping")
        else:
            if settings.email_enabled:
                send_no_picks_notification("No picks met final quality threshold")
            print("No picks met final quality threshold")

        # Also print to console
        print("\n" + format_picks_text(formatted_picks))

        logger.info("analysis_completed",
                   picks=len(formatted_picks),
                   timestamp=datetime.now().isoformat())

        return formatted_picks

    except Exception as e:
        logger.error("analysis_failed", error=str(e), exc_info=True)
        if settings.email_enabled:
            send_error_notification(str(e))
        print(f"Analysis failed: {e}")
        raise


def check_injury_updates():
    """Check for late injury updates that might affect picks.

    This runs later in the day to catch late-breaking injury news.
    """
    logger.info("injury_update_check_started")

    try:
        injuries = get_injury_report()
        # Log any notable injuries
        for team, team_injuries in injuries.items():
            out_players = [i for i in team_injuries if i.status == "out"]
            if out_players:
                logger.info("injuries_update",
                           team=team,
                           out=[i.player_name for i in out_players])

        logger.info("injury_update_check_completed")

    except Exception as e:
        logger.error("injury_update_failed", error=str(e))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="NBA Player Prop Betting Analysis System"
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start scheduler for daily automated runs"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Run analysis for specific date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis without sending email"
    )

    args = parser.parse_args()

    if args.schedule:
        from delivery.scheduler import run_scheduler
        print("Starting NBA Prop Analyzer scheduler...")
        print(f"Daily analysis will run at {settings.analysis_hour}:{settings.analysis_minute:02d} {settings.analysis_timezone}")
        run_scheduler()
    else:
        print("Running NBA Prop Analysis...")
        picks = run_analysis()
        print(f"\nGenerated {len(picks)} picks")


if __name__ == "__main__":
    main()

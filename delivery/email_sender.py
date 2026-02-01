"""
Email delivery for daily prop picks.
Uses SMTP to send formatted picks via email.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Optional
import structlog

from config.settings import get_settings
from data.models.schemas import FormattedPick
from output.formatter import format_picks_html, format_picks_text

logger = structlog.get_logger()
settings = get_settings()


def send_email_report(
    picks: List[FormattedPick],
    recipient: Optional[str] = None
) -> bool:
    """Send formatted picks via email.

    Args:
        picks: List of formatted picks
        recipient: Email recipient (defaults to settings)

    Returns:
        True if successful, False otherwise
    """
    recipient = recipient or settings.email_recipient

    if not recipient:
        logger.error("no_email_recipient", msg="EMAIL_RECIPIENT not configured")
        return False

    if not settings.email_username or not settings.email_password:
        logger.error("email_not_configured", msg="EMAIL_USERNAME or EMAIL_PASSWORD not set")
        return False

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"NBA Props - {datetime.now().strftime('%B %d, %Y')}"
        msg["From"] = f"{settings.email_from_name} <{settings.email_username}>"
        msg["To"] = recipient

        # Add plain text version
        text_content = format_picks_text(picks)
        part1 = MIMEText(text_content, "plain")
        msg.attach(part1)

        # Add HTML version
        html_content = format_picks_html(picks)
        part2 = MIMEText(html_content, "html")
        msg.attach(part2)

        # Send email
        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port) as server:
            server.starttls()
            server.login(settings.email_username, settings.email_password)
            server.sendmail(
                settings.email_username,
                recipient,
                msg.as_string()
            )

        logger.info("email_sent", recipient=recipient, picks_count=len(picks))
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error("email_auth_failed", error=str(e),
                    msg="Check EMAIL_USERNAME and EMAIL_PASSWORD (use app password for Gmail)")
        return False
    except smtplib.SMTPException as e:
        logger.error("email_smtp_error", error=str(e))
        return False
    except Exception as e:
        logger.error("email_failed", error=str(e))
        return False


def send_error_notification(
    error_message: str,
    recipient: Optional[str] = None
) -> bool:
    """Send error notification when pipeline fails.

    Args:
        error_message: Error details
        recipient: Email recipient

    Returns:
        True if successful
    """
    recipient = recipient or settings.email_recipient

    if not recipient or not settings.email_username:
        return False

    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"NBA Props ERROR - {datetime.now().strftime('%B %d, %Y')}"
        msg["From"] = f"{settings.email_from_name} <{settings.email_username}>"
        msg["To"] = recipient

        body = f"""
NBA Prop Analyzer encountered an error.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Error Details:
{error_message}

Please check the logs for more information.
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port) as server:
            server.starttls()
            server.login(settings.email_username, settings.email_password)
            server.sendmail(
                settings.email_username,
                recipient,
                msg.as_string()
            )

        logger.info("error_notification_sent", recipient=recipient)
        return True

    except Exception as e:
        logger.error("error_notification_failed", error=str(e))
        return False


def send_no_picks_notification(
    reason: str = "No quality plays identified",
    recipient: Optional[str] = None
) -> bool:
    """Send notification when no picks are available.

    Args:
        reason: Why no picks today
        recipient: Email recipient

    Returns:
        True if successful
    """
    recipient = recipient or settings.email_recipient

    if not recipient or not settings.email_username:
        return False

    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"NBA Props - No Plays Today ({datetime.now().strftime('%B %d')})"
        msg["From"] = f"{settings.email_from_name} <{settings.email_username}>"
        msg["To"] = recipient

        body = f"""
NBA Prop Analyzer - {datetime.now().strftime('%B %d, %Y')}

No picks today.

Reason: {reason}

The system found no props meeting our quality threshold. This can happen when:
- No clear edges exist in today's matchups
- Minutes situations are too uncertain
- Prop lines are already well-priced

We prioritize quality over quantity.

Tomorrow's analysis will run at the scheduled time.
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port) as server:
            server.starttls()
            server.login(settings.email_username, settings.email_password)
            server.sendmail(
                settings.email_username,
                recipient,
                msg.as_string()
            )

        logger.info("no_picks_notification_sent", recipient=recipient)
        return True

    except Exception as e:
        logger.error("no_picks_notification_failed", error=str(e))
        return False

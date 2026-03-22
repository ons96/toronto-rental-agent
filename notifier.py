"""Telegram notification module.

Sends top-N daily matches as Telegram messages with photo + scores + link.
"""
import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _score_stars(score: float) -> str:
    """Convert 0-10 score to star emoji string."""
    filled = round(score / 2)  # 0-5 stars
    return "★" * filled + "☆" * (5 - filled)


def _build_caption(listing: Dict) -> str:
    """Build Telegram message caption (max 1024 chars)."""
    clf = listing  # classification fields are at top level after DB fetch
    score = listing.get("score", 0)
    price = listing.get("price", 0)
    source = listing.get("source", "").upper()
    title = listing.get("title", "Untitled")[:60]
    address = listing.get("address", "")[:60]
    transit = listing.get("nearest_transit", "")
    dist_m = listing.get("transit_dist_m") or 0
    dist_str = f"{int(dist_m)}m" if dist_m else "?"
    private = "✅ Private room" if clf.get("private_room") else "❌ Shared room"
    occupants = clf.get("occupants", "?")
    clean = clf.get("cleanliness", "?")
    landlord = clf.get("landlord_vibe", "?")
    scam = clf.get("scam_risk", "?")
    reasoning = clf.get("reasoning", "")[:200]
    url = listing.get("url", "")

    lines = [
        f"🏠 *{title}*",
        f"💰 ${price:,}/mo | 📍 {address}",
        f"🚇 {dist_str} to {transit}",
        f"{private} | 👥 ~{occupants} people",
        f"⭐ Score: {score:.1f}/10 {_score_stars(score)}",
        f"🧹 Clean: {clean}/5 | 🤝 Landlord: {landlord}/5 | 🚨 Scam risk: {scam}/5",
        f"\n_{reasoning}_",
        f"\n[📎 View on {source}]({url})",
    ]
    caption = "\n".join(lines)
    return caption[:1024]


async def _send_listing(bot, chat_id: str, listing: Dict):
    """Send a single listing to Telegram."""
    caption = _build_caption(listing)
    image_url = listing.get("image_url", "")

    try:
        if image_url and image_url.startswith("http"):
            await bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption,
                parse_mode="Markdown",
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )
    except Exception as e:
        # Photo might fail (expired URL, private, etc.) - fall back to text
        logger.warning(f"[notifier] Photo send failed ({e}), falling back to text")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )
        except Exception as e2:
            logger.error(f"[notifier] Text send also failed: {e2}")


async def send_listings_async(listings: List[Dict], config: Dict):
    """Send top listings via Telegram bot."""
    from telegram import Bot
    from telegram.error import TelegramError

    token = config.get("telegram_token", "")
    chat_id = str(config.get("telegram_chat_id", ""))

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("[notifier] Telegram token not configured, skipping notifications")
        return

    bot = Bot(token=token)

    if not listings:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="🔍 Toronto Rental Agent: No new listings matching your criteria this run.",
            )
        except TelegramError as e:
            logger.error(f"[notifier] Failed to send empty-result message: {e}")
        return

    # Send header
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"🏙️ *Toronto Rental Agent* — Top {len(listings)} new matches!",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    for listing in listings:
        await _send_listing(bot, chat_id, listing)
        await asyncio.sleep(1)  # Telegram rate limit: 1 msg/sec


def send_listings(listings: List[Dict], config: Dict):
    """Sync wrapper for send_listings_async."""
    asyncio.run(send_listings_async(listings, config))

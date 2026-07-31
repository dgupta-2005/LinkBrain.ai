import os
import re
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from sqlmodel import Session

from database import engine
from models import SavedItem
from services import UserRepository, ItemRepository, SummarizerFactory
from ai_agent import categorize_and_summarize

user_repo = UserRepository()
item_repo = ItemRepository()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)

    if context.args:
        token = context.args[0]
        user = user_repo.get_by_link_token(token)

        if not user or (user.link_token_expires_at and user.link_token_expires_at < datetime.utcnow()):
            await update.message.reply_text("❌ This connection link has expired or is invalid. Please generate a new link on your web dashboard.")
            return

        existing = user_repo.get_by_telegram_chat_id(chat_id)
        if existing and existing.id != user.id:
            await update.message.reply_text(f"⚠️ Your Telegram is already linked to another account ('{existing.username}').")
            return

        with Session(engine) as session:
            db_user = session.get(user.__class__, user.id)
            db_user.telegram_chat_id = chat_id
            db_user.link_token = None
            db_user.link_token_expires_at = None
            session.add(db_user)
            session.commit()

        await update.message.reply_text(f"🎉 **Success!** Your Telegram is now linked to **{user.username}**.")
        return

    user = user_repo.get_by_telegram_chat_id(chat_id)
    if user:
        await update.message.reply_text(f"Welcome back, {user.username}! Send me any link to save it.")
    else:
        await update.message.reply_text("Hello! I'm bunnyBot. 🚀 Please click 'Connect Telegram' on your LinkBrain dashboard to link your account!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    text = update.message.text

    user = user_repo.get_by_telegram_chat_id(chat_id)
    if not user:
        await update.message.reply_text("⚠️ Account not linked. Please log into your web dashboard and click 'Connect Telegram'.")
        return

    urls = re.findall(r'(https?://[^\s]+)', text)
    if not urls:
        await update.message.reply_text("No valid links found in message.")
        return

    await update.message.reply_text("Processing your link...")

    for url in urls:
        platform = SummarizerFactory.detect_platform_name(url)
        ai_result = categorize_and_summarize(text=text, url=url)

        new_item = SavedItem(
            url=url,
            platform=platform,
            summary=ai_result.get("summary", "No summary available."),
            category=ai_result.get("category", "Uncategorized"),
            raw_text=text,
            user_id=user.id
        )
        item_repo.add(new_item)
        await update.message.reply_text(f"✅ Saved to your '{new_item.category}' bucket!\nSummary: {new_item.summary}")


async def start_bot():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("TELEGRAM_BOT_TOKEN not found. Bot skipped.")
        return

    application = Application.builder().token(bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bunny Bot Polling initialized...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()
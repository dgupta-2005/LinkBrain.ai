import os
import re
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from sqlmodel import Session, select
from database import engine
from models import SavedItem, User
from ai_agent import categorize_and_summarize

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)

    # 1. Check if user opened bot via 1-click Deep Link (e.g., /start connect_xyz)
    if context.args:
        token = context.args[0]
        
        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.link_token == token)
            ).first()

            # Verify token validity and expiration
            if not user or (user.link_token_expires_at and user.link_token_expires_at < datetime.utcnow()):
                await update.message.reply_text("❌ This connection link has expired or is invalid. Please click the button again from your web dashboard.")
                return

            # Check if Telegram is already linked to another user
            existing = session.exec(
                select(User).where(User.telegram_chat_id == chat_id)
            ).first()
            
            if existing and existing.id != user.id:
                await update.message.reply_text(f"⚠️ Your Telegram is already linked to another account ('{existing.username}').")
                return
    
            # Pair account & consume token
            user.telegram_chat_id = chat_id
            user.link_token = None
            user.link_token_expires_at = None
            
            session.add(user)
            session.commit()

            await update.message.reply_text(
                f"🎉 **Success!** Your Telegram is now linked to **{user.username}**.\n\n"
                f"Send me any social media link and I'll summarize it directly onto your dashboard!"
            )
            return

    # 2. Fallback /start (without payload)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.telegram_chat_id == chat_id)).first()
        if user:
            await update.message.reply_text(f"Welcome back, {user.username}! Send me any link to save it.")
        else:
            await update.message.reply_text(
                "Hello! I'm bunnyBot. 🚀\n\n"
                "Please log into your LinkBrain.ai dashboard and click 'Connect Telegram' to pair your account!"
            )

async def link_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide your link code. Example: `/link A1B2C3`")
        return
        
    code = context.args[0].upper()
    chat_id = str(update.message.chat_id)
    
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.telegram_chat_id == chat_id)).first()
        if existing:
            await update.message.reply_text(f"Your Telegram is already linked to the account '{existing.username}'.")
            return
            
        user = session.exec(select(User).where(User.link_code == code)).first()
        if not user:
            await update.message.reply_text("Invalid link code. Please check your web dashboard.")
            return
            
        user.telegram_chat_id = chat_id
        session.add(user)
        session.commit()
        
    await update.message.reply_text(f"✅ Success! Your Telegram is now linked to your web account '{user.username}'. Send me a link to save it!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    text = update.message.text
    
    with Session(engine) as session:
        user = session.exec(select(User).where(User.telegram_chat_id == chat_id)).first()
        user_id = user.id if user else None
        
    if not user_id:
        await update.message.reply_text("⚠️ Your account is not linked. Please log into your web dashboard and click 'Connect Telegram'.")
        return

    urls = re.findall(r'(https?://[^\s]+)', text)
    
    if not urls:
        await update.message.reply_text("I didn't find any links in your message. Please send a valid link!")
        return

    await update.message.reply_text("Processing your link...")
    
    for url in urls:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        if "instagram.com" in domain:
            platform = "Instagram"
        elif "twitter.com" in domain or "x.com" in domain:
            platform = "Twitter"
        elif "youtube.com" in domain or "youtu.be" in domain:
            platform = "YouTube"
        elif "linkedin.com" in domain:
            platform = "LinkedIn"
        else:
            try:
                parts = domain.split('.')
                if parts[0] in ['www', 'm', 'en', 'hi', 'mobile'] and len(parts) > 1:
                    main_word = parts[1]
                else:
                    main_word = parts[0]
                platform = main_word.title()
            except Exception:
                platform = "Web"
        
        ai_result = categorize_and_summarize(text=text, url=url)
        
        new_item = SavedItem(
            url=url,
            platform=platform,
            summary=ai_result.get("summary", "No summary available."),
            category=ai_result.get("category", "Uncategorized"),
            raw_text=text,
            user_id=user_id
        )
        
        with Session(engine) as session:
            session.add(new_item)
            session.commit()
            session.refresh(new_item)
            
        await update.message.reply_text(f"✅ Saved to your '{new_item.category}' bucket!\nSummary: {new_item.summary}")

async def start_bot():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("TELEGRAM_BOT_TOKEN not found. Bot will not start.")
        return
        
    application = Application.builder().token(bot_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("link", link_account))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Bunny Bot Polling initialized...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keeps background task active inside FastAPI lifespan
    await asyncio.Event().wait()
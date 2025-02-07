import os
import json
import logging
from contextlib import asynccontextmanager

import asyncio
from fastapi import FastAPI, Request
import uvicorn
from telegram import Update
from telegram.ext import Application
from dotenv import load_dotenv

from utils import (
    start, upload_document, my_quizzes, all_quizzes, 
    start_quiz_conversation, quiz_answer_handler, 
    cancel_quiz, quit_quiz, setup_handlers, QUIZ_TAKING
)

# Load environment variables first
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
API_TOKEN = os.getenv('BOT_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8000))

# Initialize bot application
application = Application.builder().token(API_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for FastAPI application"""
    try:
        # Startup: Set up webhook and initialize application
        await setup_handlers(application)  # Pass the application instance
        webhook_info = await application.bot.get_webhook_info()
        if webhook_info.url != WEBHOOK_URL:
            await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}")
        await application.initialize()
        await application.start()
        logger.info("Bot started with webhook")
        
        yield
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise
    finally:
        # Shutdown: Clean up
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped")

# Create FastAPI app with lifespan handler
app = FastAPI(lifespan=lifespan)

@app.post(f"/{API_TOKEN}")
async def webhook_handler(request: Request):
    """Handle incoming webhook updates from Telegram."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )
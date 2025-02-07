import os
import json
import logging
from contextlib import asynccontextmanager

import asyncio
from fastapi import FastAPI, Request
import uvicorn
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

from utils import start, upload_document, my_quizzes, all_quizzes, start_quiz_conversation, send_next_quiz_question, quiz_answer_handler, cancel_quiz, quit_quiz, QUIZ_TAKING


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Set up webhook and initialize application
    await setup_handlers()
    webhook_info = await application.bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}")
    await application.initialize()
    await application.start()
    logger.info("Bot started with webhook")
    
    yield  # Server is running
    
    # Shutdown: Clean up
    await application.stop()
    await application.shutdown()
    logger.info("Bot stopped")

# FastAPI app with lifespan handler
app = FastAPI(lifespan=lifespan)


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)



API_TOKEN = os.getenv('BOT_API_KEY')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{API_TOKEN}'
CHAT_ID = int(os.getenv('CHAT_ID'))
PORT = int(os.getenv('PORT', 8000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')


# Initialize bot application
application = Application.builder().token(API_TOKEN).build()



# Register all handlers (same as before)
async def setup_handlers():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myquizzes", my_quizzes))
    application.add_handler(CommandHandler("allquizzes", all_quizzes))
    application.add_handler(CommandHandler("quit", quit_quiz))
    application.add_handler(MessageHandler(filters.Document.ALL, upload_document))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_quiz_conversation, pattern=r"^takequiz_\d+$")],
        states={
            QUIZ_TAKING: [
                CallbackQueryHandler(quiz_answer_handler, pattern=r"^(answer_\d+|restart_quiz)$"),
                CommandHandler("quit", quit_quiz),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz), CommandHandler("quit", quit_quiz)],
    )
    application.add_handler(conv_handler)

# FastAPI webhook endpoint
@app.post(f"/{API_TOKEN}")
async def webhook_handler(request: Request):
    """Handle incoming webhook updates from Telegram."""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# Health check endpoint
@app.get("/")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}



# # ---------------------------
# # Main Function
# # ---------------------------
# def main() -> None:
#     """Start the bot."""  # Replace with your bot's token
#     application = Application.builder().token(API_TOKEN).build()

#     # Register command handlers.
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(CommandHandler("myquizzes", my_quizzes))
#     application.add_handler(CommandHandler("allquizzes", all_quizzes))
#     application.add_handler(CommandHandler("quit", quit_quiz))

#     # Handle JSON file uploads.
#     application.add_handler(MessageHandler(filters.Document.ALL, upload_document))

#     # Conversation handler for taking quizzes.
#     conv_handler = ConversationHandler(
#         entry_points=[CallbackQueryHandler(start_quiz_conversation, pattern=r"^takequiz_\d+$")],
#         states={
#             QUIZ_TAKING: [
#                 CallbackQueryHandler(quiz_answer_handler, pattern=r"^(answer_\d+|restart_quiz)$"),
#                 CommandHandler("quit", quit_quiz),
#             ]
#         },
#         fallbacks=[CommandHandler("cancel", cancel_quiz), CommandHandler("quit", quit_quiz)],
#     )
#     application.add_handler(conv_handler)

#     # Run the bot.
#     application.run_polling()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )
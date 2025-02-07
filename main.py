import os
import json
import logging
import sqlite3
import random
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn
from telegram import Update
from telegram.ext import Application
from dotenv import load_dotenv
from utils import (
    start, upload_document, my_quizzes, all_quizzes,
    start_quiz_conversation, quiz_answer_handler, cancel_quiz,
    quit_quiz, setup_handlers, QUIZ_TAKING
)

# Load environment variables
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
DB_FILE = "quizzes.db"

# Initialize bot application
application = Application.builder().token(API_TOKEN).build()

# Database setup
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            questions TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_quiz(name, creator_id, questions):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO quizzes (name, creator_id, questions) VALUES (?, ?, ?)",
        (name, creator_id, json.dumps(questions))
    )
    conn.commit()
    conn.close()

def get_all_quizzes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM quizzes")
    quizzes = cursor.fetchall()
    conn.close()
    return quizzes

def get_quiz_by_id(quiz_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT questions FROM quizzes WHERE id = ?", (quiz_id,))
    quiz = cursor.fetchone()
    conn.close()
    if quiz:
        questions = json.loads(quiz[0])
        random.shuffle(questions)
        return questions
    return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        await setup_handlers(application)
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
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped")

# Create FastAPI app with lifespan handler
app = FastAPI(lifespan=lifespan)

@app.post(f"/{API_TOKEN}")
async def webhook_handler(request: Request):
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
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )

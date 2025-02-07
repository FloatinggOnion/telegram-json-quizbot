import os
import requests
import json
import logging
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
)
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import uvicorn
from dotenv import load_dotenv


load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# State for our conversation handler
QUIZ = 1

API_TOKEN = os.getenv('BOT_API_KEY')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{API_TOKEN}'
CHAT_ID = int(os.getenv('CHAT_ID'))
JSON_FILE = os.getenv('')


app = FastAPI()


# Global variable for quiz questions
# Initially empty; a default question will be used if no file is uploaded.
QUIZ_QUESTIONS = []

@app.post("/upload-quiz/")
async def upload_quiz(file: UploadFile = File(...)):
    """
    Endpoint to upload a JSON file containing quiz questions.
    The JSON should be a list of questions in the following format:
    
      Format 1:
        {
            "question": <question text>,
            "options": [option_1, option_2, option_3, option_4],
            "correct_option": <index_of_correct_option (0-based)>
        }
        
      (Also acceptable are scripture or note formats as needed.)
    """
    file_contents = await file.read()
    try:
        data = json.loads(file_contents)
        if not isinstance(data, list):
            return JSONResponse(status_code=400, content={"error": "JSON must be a list of questions."})
        # Update the global quiz questions
        global QUIZ_QUESTIONS
        QUIZ_QUESTIONS = data
        return {"status": "Quiz updated successfully", "num_questions": len(QUIZ_QUESTIONS)}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON file provided", "details": str(e)})

# -------------------------
# Telegram Bot Setup
# -------------------------
# Enable logging for the bot
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define conversation state
QUIZ = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start command handler sends a welcome message with a "Start Quiz" button.
    """
    welcome_text = (
        "Welcome to the Quiz Bot!\n\n"
        "Test your knowledge with our quiz. "
        "Press the button below to start."
    )
    keyboard = [[InlineKeyboardButton("Start Quiz", callback_data="start_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)
    return QUIZ

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Initializes quiz state and sends the first question.
    """
    query = update.callback_query
    await query.answer()
    # Initialize user data for the quiz
    context.user_data["score"] = 0
    context.user_data["current_q"] = 0
    await send_next_question(query, context)
    return QUIZ

async def send_next_question(query, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends the next question from QUIZ_QUESTIONS (or a default question if none uploaded).
    """
    current_q = context.user_data.get("current_q", 0)
    global QUIZ_QUESTIONS
    # Use uploaded quiz questions if available; otherwise, use a default question.
    if not QUIZ_QUESTIONS:
        questions = [{
            "question": "Default question: What is 2+2?",
            "options": ["3", "4", "5", "6"],
            "correct_option": 1
        }]
    else:
        questions = QUIZ_QUESTIONS

    if current_q < len(questions):
        q = questions[current_q]
        # Build inline keyboard for answer options
        keyboard = [
            [InlineKeyboardButton(option, callback_data=f"answer_{idx}")]
            for idx, option in enumerate(q["options"])
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(q["question"], reply_markup=reply_markup)
    else:
        # Quiz finished; show the score and offer restart
        score = context.user_data.get("score", 0)
        total = len(questions)
        text = f"Quiz Completed!\nYour score: {score}/{total}\nWould you like to start again?"
        keyboard = [[InlineKeyboardButton("Restart Quiz", callback_data="restart")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(text, reply_markup=reply_markup)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes answer selection and handles the restart option.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    global QUIZ_QUESTIONS
    if not QUIZ_QUESTIONS:
        questions = [{
            "question": "Default question: What is 2+2?",
            "options": ["3", "4", "5", "6"],
            "correct_option": 1
        }]
    else:
        questions = QUIZ_QUESTIONS

    if data.startswith("answer_"):
        selected = int(data.split("_")[1])
        current_q = context.user_data.get("current_q", 0)
        q = questions[current_q]
        if selected == q["correct_option"]:
            context.user_data["score"] += 1
            feedback = "Correct!"
        else:
            correct_answer = q["options"][q["correct_option"]]
            feedback = f"Wrong! The correct answer was: {correct_answer}"
        await query.message.reply_text(feedback)
        context.user_data["current_q"] = current_q + 1
        await send_next_question(query, context)
    elif data == "restart":
        # Reset and restart quiz
        context.user_data["score"] = 0
        context.user_data["current_q"] = 0
        await send_next_question(query, context)
    return QUIZ

def run_telegram_bot():
    """
    Initializes and runs the Telegram bot.
    """
    BOT_TOKEN = "YOUR_BOT_TOKEN"
    application = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            QUIZ: [
                CallbackQueryHandler(start_quiz, pattern="^start_quiz$"),
                CallbackQueryHandler(handle_answer, pattern="^(answer_|restart)")
            ]
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv_handler)
    application.run_polling()

# -------------------------
# Running Both FastAPI and Telegram Bot
# -------------------------
if __name__ == "__main__":
    # Run Telegram bot in a separate thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Run FastAPI using Uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
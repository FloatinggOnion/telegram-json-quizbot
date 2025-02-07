import os
import json
import logging
import asyncio
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


load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global storage for quizzes.
# Each quiz is stored as:
#   quiz_id (int) : {"name": <quiz name>, "creator_id": <user id>, "questions": [list of questions]}
# A question is expected to be a dict with keys: "question", "options", "correct_option"
quizzes = {}
leaderboard = {}  # Stores user scores {user_id: {"name": "John", "score": 5, "total": 10}}
next_quiz_id = 1  # Auto-increment quiz id

# Conversation state for taking a quiz
QUIZ_TAKING = 1
QUESTION_TIMEOUT = 20  # Time limit for answering a question (in seconds)

API_TOKEN = os.getenv('BOT_API_KEY')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{API_TOKEN}'
CHAT_ID = int(os.getenv('CHAT_ID'))
JSON_FILE = os.getenv('')


# ---------------------------
# Bot Command Handlers
# ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message and instructions."""
    text = (
        "Welcome to the Quiz Bot\!\n\n"
        "• To create a quiz, simply upload a JSON file containing your questions.\n"
        "   The JSON must be a list of questions. Each question should follow one of these formats:\n\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "question": "What is the capital of France?",\n'
        '    "options": ["London", "Paris", "Berlin", "Rome"],\n'
        '    "correct_option": 1\n'
        "  },\n"
        "  {\n"
        '    "question": "John 3:16",\n'
        '    "options": ["Matthew 5:14", "John 3:16", "Luke 1:2", "Acts 2:38"],\n'
        '    "correct_option": 1\n'
        "  },\n"
        "  {\n"
        '    "question": "Point from notes on Romans 12",\n'
        '    "options": ["Romans 12:1", "Romans 12:2", "Romans 12:3", "Romans 12:4"],\n'
        '    "correct_option": 0\n'
        "  }\n"
        "]\n"
        "```\n\n"
        "**Explanation of JSON Structure:**\n"
        "* **`question`**: The question text (or scripture quote/note point).\n"
        "* **`options`**: An array of possible answers.\n"
        "* **`correct_option`**: The index (starting from 0) of the correct answer in the `options` array.\n\n"
        "• Use `/myquizzes` to see quizzes you’ve created.\n"
        "• Use `/allquizzes` to browse all quizzes and take one.\n"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")

async def upload_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document uploads (expecting JSON files) to create quizzes."""
    document = update.message.document
    if document.file_name.endswith(".json"):
        file = await document.get_file()
        file_bytes = await file.download_as_bytearray()
        try:
            data = json.loads(file_bytes.decode("utf-8"))
            if not isinstance(data, list):
                await update.message.reply_text("The JSON must be a list of questions.")
                return

            # Use the file name (without extension) as the quiz name.
            quiz_name = document.file_name.rsplit(".", 1)[0]
            global next_quiz_id
            quiz_id = next_quiz_id
            next_quiz_id += 1

            # Save quiz details (you can add validation of question structure if desired)
            quizzes[quiz_id] = {
                "name": quiz_name,
                "creator_id": update.effective_user.id,
                "questions": data
            }
            # Send success message with inline button
            keyboard = [[InlineKeyboardButton("Start Quiz", callback_data=f"takequiz_{quiz_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Quiz '{quiz_name}' created successfully!\nPress the button below to start.",
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(f"Error parsing JSON: {e}")
    else:
        await update.message.reply_text("Please upload a file with a .json extension.")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List quizzes created by the current user."""
    user_id = update.effective_user.id
    user_quizzes = [f"ID: {quiz_id} - {quiz['name']}" 
                    for quiz_id, quiz in quizzes.items() if quiz["creator_id"] == user_id]
    if not user_quizzes:
        await update.message.reply_text("You haven't created any quizzes yet.")
    else:
        text = "Your quizzes:\n" + "\n".join(user_quizzes)
        await update.message.reply_text(text)

async def all_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all available quizzes with an inline button to take each quiz."""
    if not quizzes:
        await update.message.reply_text("No quizzes available yet.")
    else:
        buttons = []
        for quiz_id, quiz in quizzes.items():
            button = InlineKeyboardButton(f"{quiz['name']} (ID: {quiz_id})", callback_data=f"takequiz_{quiz_id}")
            buttons.append([button])
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Available quizzes:", reply_markup=reply_markup)
        

# ---------------------------
# Quiz Taking Conversation Handlers
# ---------------------------

async def start_quiz_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for taking a quiz.
    Triggered by the inline button in /allquizzes (callback_data: "takequiz_{quiz_id}")
    """
    query = update.callback_query
    await query.answer()
    data = query.data  # Expected format: "takequiz_{quiz_id}"
    try:
        quiz_id = int(data.split("_")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Invalid quiz ID.")
        return ConversationHandler.END

    if quiz_id not in quizzes:
        await query.message.reply_text("Quiz not found.")
        return ConversationHandler.END

    # Store the selected quiz and initialize quiz state in user_data.
    context.user_data["current_quiz"] = quizzes[quiz_id]
    context.user_data["quiz_id"] = quiz_id
    context.user_data["current_q"] = 0
    context.user_data["score"] = 0

    await send_next_quiz_question(query, context)
    return QUIZ_TAKING

async def send_next_quiz_question(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the next question or finish the quiz."""
    quiz = context.user_data.get("current_quiz")
    current_q = context.user_data.get("current_q", 0)

    if current_q < len(quiz["questions"]):
        q = quiz["questions"][current_q]
        keyboard = [
            [InlineKeyboardButton(option, callback_data=f"answer_{idx}")]
            for idx, option in enumerate(q["options"])
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(q["question"], reply_markup=reply_markup)

        # Start question timer
        await asyncio.sleep(QUESTION_TIMEOUT)
        if context.user_data.get("current_q") == current_q:  # Check if user answered
            context.user_data["current_q"] += 1  # Move to next question
            await query.message.reply_text("⏳ Time's up! Moving to the next question.")
            await send_next_quiz_question(query, context)

    else:
        # 🎯 Quiz finished: Update leaderboard
        user_id = query.from_user.id
        user_name = query.from_user.first_name
        score = context.user_data.get("score", 0)
        total = len(quiz["questions"])

        leaderboard[user_id] = {"name": user_name, "score": score, "total": total}

        # 🏆 Generate leaderboard ranking
        sorted_leaderboard = sorted(
            leaderboard.items(), key=lambda x: x[1]["score"], reverse=True
        )
        ranking_text = "🏅 *Leaderboard:*\n"
        for idx, (uid, data) in enumerate(sorted_leaderboard[:5], start=1):  # Show top 5
            ranking_text += f"{idx}. {data['name']} - {data['score']}/{data['total']} 🎯\n"

        text = f"🎉 *Quiz Completed!*\nYour score: {score}/{total}\n\n{ranking_text}"
        keyboard = [[InlineKeyboardButton("Restart Quiz", callback_data="restart_quiz")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def quiz_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle answer selection and provide animated feedback."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("answer_"):
        selected = int(data.split("_")[1])
        quiz = context.user_data.get("current_quiz")
        current_q = context.user_data.get("current_q", 0)
        q = quiz["questions"][current_q]

        # 🌟 Check if the answer is correct
        if selected == q["correct_option"]:
            context.user_data["score"] += 1
            feedback = f"✅ Correct! 🎉\n\n🎯 *{q['question']}*\n✅ {q['options'][selected]}"
            gif_url = "https://media.giphy.com/media/26gN1h5bQPSF7vsoI/giphy.gif"
        else:
            correct_ans = q["options"][q["correct_option"]]
            feedback = f"❌ Wrong! The correct answer was:\n\n✅ {correct_ans}"
            gif_url = "https://media.giphy.com/media/l3vR85PnGsBwu1PFK/giphy.gif"

        # 🌟 Send animation first
        await query.message.reply_animation(gif_url)

        # 🌟 Send feedback message
        await query.message.reply_text(feedback, parse_mode="Markdown")

        # Move to next question
        context.user_data["current_q"] += 1
        await send_next_quiz_question(query, context)

    elif data == "restart_quiz":
        # Reset quiz state for restart
        context.user_data["current_q"] = 0
        context.user_data["score"] = 0
        await send_next_quiz_question(query, context)
        return QUIZ_TAKING

    return QUIZ_TAKING


async def cancel_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current quiz conversation."""
    if update.message:
        await update.message.reply_text("Quiz cancelled.")
    return ConversationHandler.END

async def quit_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stops the quiz and resets the user's progress."""
    context.user_data.clear()  # Reset user progress

    # If the user sent "/quit" as a message
    if update.message:
        await update.message.reply_text("❌ You have quit the quiz. Type /start to play again.")
    else:  
        # If the user pressed an inline button (just in case)
        query = update.callback_query
        await query.answer()
        await query.message.reply_text("❌ You have quit the quiz. Type /start to play again.")

    return ConversationHandler.END  # Properly exit the conversation


# ---------------------------
# Main Function
# ---------------------------
def main() -> None:
    """Start the bot."""  # Replace with your bot's token
    application = Application.builder().token(API_TOKEN).build()

    # Register command handlers.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myquizzes", my_quizzes))
    application.add_handler(CommandHandler("allquizzes", all_quizzes))
    application.add_handler(CommandHandler("quit", quit_quiz))

    # Handle JSON file uploads.
    application.add_handler(MessageHandler(filters.Document.ALL, upload_document))

    # Conversation handler for taking quizzes.
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

    # Run the bot.
    application.run_polling()

if __name__ == "__main__":
    main()
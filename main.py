import os
import json
import logging
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
next_quiz_id = 1  # Auto-increment quiz id

# Conversation state for taking a quiz
QUIZ_TAKING = 1

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
        "Welcome to the Quiz Bot!\n\n"
        "• To create a quiz, simply upload a JSON file containing your questions.\n"
        "   The JSON must be a list of questions. Each question should follow one of these formats:\n"
        "      ```json\n"
        "      Format 1:\n"
        "        { \"question\": \"<question text>\", \"options\": [option1, option2, option3, option4], \"correct_option\": <0-based index> }\n"
        "      Format 2 (scripture):\n"
        "        { \"question\": \"<scripture quote>\", \"options\": [ref1, ref2, ref3, ref4], \"correct_option\": <index> }\n"
        "      Format 3 (notes):\n"
        "        { \"question\": \"<bullet point from note>\", \"options\": [ref1, ref2, ref3, ref4], \"correct_option\": <index> }\n\n"
        "      ```\n"
        "• Use /myquizzes to see quizzes you’ve created.\n"
        "• Use /allquizzes to browse all quizzes and take one.\n"
    )
    await update.message.reply_text(text)

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
    """Send the next question from the current quiz or finish if done."""
    quiz = context.user_data.get("current_quiz")
    current_q = context.user_data.get("current_q", 0)

    if current_q < len(quiz["questions"]):
        q = quiz["questions"][current_q]
        # Build an inline keyboard for the options.
        keyboard = [
            [InlineKeyboardButton(option, callback_data=f"answer_{idx}")]
            for idx, option in enumerate(q["options"])
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(q["question"], reply_markup=reply_markup)
    else:
        # Quiz finished; show final score and offer to restart.
        score = context.user_data.get("score", 0)
        total = len(quiz["questions"])
        text = f"Quiz Completed!\nYour score: {score}/{total}\nWould you like to restart the quiz?"
        keyboard = [[InlineKeyboardButton("Restart Quiz", callback_data="restart_quiz")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(text, reply_markup=reply_markup)

async def quiz_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle answer selection during a quiz conversation."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("answer_"):
        selected = int(data.split("_")[1])
        quiz = context.user_data.get("current_quiz")
        current_q = context.user_data.get("current_q", 0)
        q = quiz["questions"][current_q]

        if selected == q["correct_option"]:
            context.user_data["score"] += 1
            feedback = "Correct!"
        else:
            correct_ans = q["options"][q["correct_option"]]
            feedback = f"Wrong! The correct answer was: {correct_ans}"

        await query.message.reply_text(feedback)
        context.user_data["current_q"] = current_q + 1
        await send_next_quiz_question(query, context)
        return QUIZ_TAKING

    elif data == "restart_quiz":
        # Reset quiz state for a restart.
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

    # Handle JSON file uploads.
    application.add_handler(MessageHandler(filters.Document.ALL, upload_document))

    # Conversation handler for taking quizzes.
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_quiz_conversation, pattern=r"^takequiz_\d+$")],
        states={
            QUIZ_TAKING: [
                CallbackQueryHandler(quiz_answer_handler, pattern=r"^(answer_\d+|restart_quiz)$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)],
    )
    application.add_handler(conv_handler)

    # Run the bot.
    application.run_polling()

if __name__ == "__main__":
    main()
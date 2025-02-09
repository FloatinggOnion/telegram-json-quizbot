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
import asyncio

logger = logging.getLogger(__name__)

# Global storage
quizzes = {}
leaderboard = {}
next_quiz_id = 1

# Constants
QUIZ_TAKING = 1
QUESTION_TIMEOUT = 20

async def setup_handlers(application: Application):
    """Set up all handlers for the bot."""
    try:
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
        logger.info("All handlers have been set up successfully")
    except Exception as e:
        logger.error(f"Error setting up handlers: {e}")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message and instructions."""
    try:
        text = (
            "Welcome to the Onion Quiz Bot! 🎯\n\n"
            "To create a quiz, upload a JSON file with your questions. Format:\n\n"
            "```\n"
            "[\n"
            "  {\n"
            '    "question": "What is 2+2?",\n'
            '    "options": ["3", "4", "5", "6"],\n'
            '    "correct_option": 1\n'
            "  }\n"
            "]\n"
            "```\n\n"
            "Commands:\n"
            "• /myquizzes - See your quizzes\n"
            "• /allquizzes - Browse all quizzes\n"
            "• /quit - Exit current quiz"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
        logger.info(f"Start command executed for user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use /help to see available commands.")

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
    """List quizzes created by the current user with inline buttons."""
    user_id = update.effective_user.id
    user_quizzes = [
        (quiz_id, quiz)
        for quiz_id, quiz in quizzes.items()
        if quiz["creator_id"] == user_id
    ]

    if not user_quizzes:
        await update.message.reply_text("You haven't created any quizzes yet.")
        return

    buttons = []
    for quiz_id, quiz in user_quizzes:
        num_questions = len(quiz["questions"])
        button = InlineKeyboardButton(
            f"{quiz['name']} (ID: {quiz_id}, {num_questions} questions)",
            callback_data=f"takequiz_{quiz_id}",
        )
        buttons.append([button])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Your quizzes:", reply_markup=reply_markup)

async def all_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all available quizzes with an inline button to take each quiz."""
    if not quizzes:
        await update.message.reply_text("No quizzes available yet.")
    else:
        buttons = []
        for quiz_id, quiz in quizzes.items():
            num_questions = len(quiz["questions"])
            button = InlineKeyboardButton(f"{quiz['name']} (ID: {quiz_id}, {num_questions} questions)", callback_data=f"takequiz_{quiz_id}")
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

        # Remove the timer for now as it's causing issues with webhooks
        # We can implement a different timeout mechanism if needed
        
    else:
        # Quiz finished: Update leaderboard
        user_id = query.from_user.id
        user_name = query.from_user.first_name
        score = context.user_data.get("score", 0)
        total = len(quiz["questions"])

        leaderboard[user_id] = {"name": user_name, "score": score, "total": total}

        # Generate leaderboard ranking
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
    try:
        await query.answer()  # Important: Acknowledge the button press first
        data = query.data

        if data.startswith("answer_"):
            selected = int(data.split("_")[1])
            quiz = context.user_data.get("current_quiz")
            current_q = context.user_data.get("current_q", 0)
            q = quiz["questions"][current_q]

            # Check if the answer is correct
            if selected == q["correct_option"]:
                context.user_data["score"] = context.user_data.get("score", 0) + 1
                feedback = f"✅ Correct! 🎉\n\n🎯 *{q['question']}*\n✅ {q['options'][selected]}"
            else:
                correct_ans = q["options"][q["correct_option"]]
                feedback = f"❌ Wrong! The correct answer was:\n\n✅ {correct_ans}"

            # Send feedback message
            await query.message.reply_text(feedback, parse_mode="Markdown")

            # Move to next question
            context.user_data["current_q"] += 1
            await send_next_quiz_question(query, context)

        elif data == "restart_quiz":
            # Reset quiz state for restart
            context.user_data["current_q"] = 0
            context.user_data["score"] = 0
            await send_next_quiz_question(query, context)

    except Exception as e:
        logger.error(f"Error in quiz_answer_handler: {e}")
        await query.message.reply_text("Sorry, there was an error processing your answer. Please try again.")
        return ConversationHandler.END

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
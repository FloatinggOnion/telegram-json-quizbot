import os
import requests
import json

from fastapi import FastAPI, UploadFile, File
from dotenv import load_dotenv


load_dotenv()

API_TOKEN = os.getenv('BOT_API_KEY')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{API_TOKEN}'
CHAT_ID = int(os.getenv('CHAT_ID'))
JSON_FILE = os.getenv('')


app = FastAPI()


def send_message_to_telegram(message: str):
    """
    Send a simple text message to Telegram.
    """
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    response = requests.post(url, json=payload)
    if not response.ok:
        print("Error sending message:", response.json())
    return response.json()


def send_quiz_question(question_data: dict):
    """
    Send a quiz question using Telegram's sendPoll API.
    The quiz data should include:
      - question: string
      - options: list of strings
      - correct_option: integer index of the correct answer
    """
    payload = {
        "chat_id": CHAT_ID,
        "question": question_data["question"],
        "options": question_data["options"],
        "type": "quiz",
        "correct_option_id": question_data["correct_option"]
    }
    url = f"{TELEGRAM_API_URL}/sendPoll"
    response = requests.post(url, json=payload)
    if not response.ok:
        print("Error sending quiz question:", response.json())
    return response.json()


@app.post("/upload-quiz/")
async def upload_quiz(file: UploadFile = File(...)):
    """
    Endpoint to upload a JSON file containing quiz data.
    The quiz name will be derived from the filename (without extension).
    """
    # Read file contents
    file_contents = await file.read()
    try:
        quiz_data = json.loads(file_contents)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON file provided."}
    
    # Use the filename (without extension) as the quiz name
    quiz_name = os.path.splitext(file.filename)[0]

    # Announce the start of the quiz
    send_message_to_telegram(f"Starting Quiz: {quiz_name}")

    # Send each quiz question from the JSON data
    for question in quiz_data:
        send_quiz_question(question)

    # Announce the end of the quiz
    send_message_to_telegram("Quiz Ended!")

    return {"status": "Quiz sent successfully", "quiz_name": quiz_name}
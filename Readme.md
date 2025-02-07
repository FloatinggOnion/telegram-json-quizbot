# TELEGRAM QUIZ BOT
*Author: Jesse-Paul Osemeke*
This is a FastAPI backend for a telegram quiz bot. It takes in the quiz data in a JSON format, and makes a quiz that can be shared across the plaform.

### How To Run
- Clone the repo
- Create a virtual environment
- Install the requirements
- Run the app
- Test the app by uploading a JSON file in the format:
```json
[
    {
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin", "Madrid"],
        "correct_option": 0
    },
]
```

### Features / Roadmap
- [x] Create a quiz
- [ ] Share quiz across telegram platform
- [ ] Get quiz results
- [ ] Add more quiz types
- [ ] Add more quiz options

### Problems Encountered / Bugs Squashed
- Chat not found: When I was testing on my chat...it didn't work. So I had to start a chat with it and convert the `chat_id` in code to an integer.
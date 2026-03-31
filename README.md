# Arlo Assistant

Personal AI assistant backend — conversational life management.

## Quick Start

```bash
cp .env.example .env
# Add your CLAUDE_CODE_OAUTH_TOKEN to .env
docker compose up --build -d
```

API runs on http://localhost:8002

## Chat

```bash
# Send a message
curl -X POST http://localhost:8002/chat/message \
  -H "Authorization: Bearer arlo-assistant-dev-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "I want to eat 180g of protein every day"}'

# Check response (replace with message_id from above)
curl http://localhost:8002/chat/message/<MESSAGE_ID> \
  -H "Authorization: Bearer arlo-assistant-dev-key"
```

## Features

- Conversational AI with persistent memory
- Health tracking (steps, meals, workouts, macros)
- Meal planning and grocery lists
- Task and goal management
- Habit streaks
- Smart reminders
- Knowledge storage and recall

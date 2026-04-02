# Arlo Assistant

Personal AI assistant backend for the Arlo mobile app. Manages health, fitness, nutrition, tasks, goals, habits, recipes, knowledge, and reminders through conversational AI and direct API endpoints.

## Quick Start

```bash
cp .env.example .env
# Add your CLAUDE_CODE_OAUTH_TOKEN and JWT_SECRET to .env
docker compose up --build -d
```

API runs on `http://localhost:8002`.

## Authentication

Two auth methods are supported:

**JWT (production):** Register, log in, use access tokens.
```bash
# Register
curl -X POST http://localhost:8002/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123", "name": "Varun"}'

# Login
curl -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'

# Use the access_token from login response
curl http://localhost:8002/tasks \
  -H "Authorization: Bearer <access_token>"
```

**Legacy API key (dev):** Use the static `API_KEY` from `.env` as a Bearer token. Maps to the default user.
```bash
curl http://localhost:8002/tasks \
  -H "Authorization: Bearer arlo-assistant-dev-key"
```

### Auth Endpoints

```
POST /auth/register     Register new user (email, password, name) → tokens
POST /auth/login        Login (email, password) → access_token + refresh_token
POST /auth/refresh      Refresh token → new access_token
GET  /auth/me           Get current user profile
```

Access tokens expire in 30 minutes. Refresh tokens expire in 7 days.

## API Reference

### Chat

```
POST /chat/message                      Send message (returns message_id, status=thinking)
GET  /chat/message/{id}                 Poll for response (status: thinking|complete|error)
GET  /chat/message/{id}/stream          SSE stream — real-time updates until complete
GET  /chat/conversations                List conversation threads
GET  /chat/conversations/{id}           Get messages in a conversation
```

Claude processes messages async, extracts structured actions (meal logs, tasks, reminders, knowledge), and stores them automatically. Use the SSE stream endpoint instead of polling for real-time responses.

### Health Tracking

```
POST /health/steps              Log step count (replaces daily value)
POST /health/meals              Log meal with macros (calories, protein, carbs, fat)
POST /health/workouts           Log workout with exercises and duration
GET  /health/meals              List meals for a date
GET  /health/dashboard          Today's aggregated health stats vs goals
GET  /health/weekly             7-day rolling summary with averages
```

### Tasks

```
POST   /tasks                   Create task (title, priority, due_date, category)
GET    /tasks                   List tasks (filter: ?status=todo&priority=high&category=errands)
PATCH  /tasks/{id}              Update task (status, title, priority, due_date)
DELETE /tasks/{id}              Delete task
```

Status: `todo`, `in_progress`, `done`. Priority: `low`, `medium`, `high`, `urgent`.

### Goals

```
POST   /goals                   Create goal (title, target_value, unit, deadline, category)
GET    /goals                   List goals (filter: ?category=fitness&status=active)
PATCH  /goals/{id}              Update goal (current_value auto-checks achievement)
DELETE /goals/{id}              Delete goal
```

### Habits

```
POST   /habits                  Create habit (name, frequency: daily|weekly)
GET    /habits                  List all habits with streak info
PATCH  /habits/{id}/check       Mark habit done today (auto-updates streak)
DELETE /habits/{id}             Delete habit
```

### Recipes

```
POST   /recipes                 Create recipe (name, ingredients, instructions, macros, tags)
GET    /recipes                 List recipes (filter: ?search=chicken)
GET    /recipes/{id}            Get recipe detail
DELETE /recipes/{id}            Delete recipe
```

### Grocery Lists

```
POST   /grocery-lists                        Create list with items
GET    /grocery-lists                        List all grocery lists
GET    /grocery-lists/{id}                   Get list with items
PATCH  /grocery-lists/{id}/items/{idx}/check Toggle item checked/unchecked
DELETE /grocery-lists/{id}                   Delete list
```

### Knowledge Base

```
GET    /knowledge               List stored facts (filter: ?category=preference&search=italian)
GET    /knowledge/{id}          Get single entry
DELETE /knowledge/{id}          Delete entry
```

### Reminders

```
POST   /reminders               Create reminder (time-based or smart condition)
GET    /reminders               List reminders (filter: ?status=active)
GET    /reminders/triggered     Get reminders that should fire now
PATCH  /reminders/{id}/dismiss  Dismiss a reminder
DELETE /reminders/{id}          Delete reminder
```

Smart conditions: `steps_below`, `no_meal_logged`, `habit_not_done`.

### Calendar

```
POST   /calendar/events              Create event (title, start_time, end_time, location)
GET    /calendar/events              List events (filter: ?start_date=&end_date=)
GET    /calendar/events/today        Today's events
PATCH  /calendar/events/{id}         Update event
DELETE /calendar/events/{id}         Delete event
```

### Integrations

```
GET  /integrations/runtime/workflows      List triggered Arlo Runtime workflows
GET  /integrations/runtime/workflows/{id} Get workflow status + results
POST /integrations/healthkit/sync         Push HealthKit data from iOS app
```

HealthKit sync merges steps (max of manual vs HealthKit), heart rate, sleep, active calories, and workouts.

### System

```
GET /health                     Health check (unauthenticated)
```

## Architecture

```
app/
  api/          Route handlers (auth, chat, health, tasks, goals, habits, recipes, grocery, knowledge, reminders, calendar, integrations)
  services/     Business logic (auth, chat, health, task, recipe, knowledge, reminder, calendar, runtime, weather, healthkit)
  llm/          Claude integration (subprocess wrapper, prompt builder, action parser)
  db/           SQLAlchemy async models (16 tables) + connection pooling
  core/         Config, JWT security, exceptions, middleware, logging
alembic/        Database migrations
tests/          63 API tests + unit tests
```

## Project Status & Roadmap

### Phase 1: Conversational Backend -- DONE
- Chat with Claude Code CLI, async message processing
- Action extraction (profile updates, meal logs, tasks, knowledge, reminders)
- Context-aware system prompts

### Phase 2: Health & Fitness -- DONE
- Steps, meals, workouts tracking
- Daily dashboard, weekly summaries

### Phase 3: Full Feature Set -- DONE
- Tasks, Goals, Habits CRUD with streak tracking
- Recipes and Grocery Lists
- Knowledge Base API
- Smart Reminders with condition evaluation

### Phase 4: Production Hardening -- DONE
- JWT auth with registration/login/refresh
- Multi-user support (user_id from token, per-user data isolation)
- Alembic database migrations
- CORS, request logging, error handling middleware
- Structured logging (JSON in production, human-readable in dev)
- Database connection pooling
- SSE for real-time chat streaming

### Phase 5: Integrations -- DONE
- Arlo Runtime integration (chat triggers research/trading workflows)
- Weather API (OpenWeatherMap, 30min cache, injected into chat context)
- Apple HealthKit sync endpoint (iOS pushes batches, backend merges)
- Calendar events CRUD with schedule context in chat
- Claude can create events and trigger workflows via chat actions

### Phase 6: Deployment (planned)
- Connect iOS app (Swift networking layer)
- Deploy to always-on machine (Windows + Tailscale)
- Rate limiting, monitoring, CI/CD

## Development

```bash
# Run full API test suite (63 tests)
python3 tests/test_full_api.py

# Run unit tests inside container
docker cp tests arlo-assistant-api-1:/opt/assistant/tests
docker compose exec api pip install pytest pytest-asyncio -q
docker compose exec api python3 -m pytest tests/ -v

# Run migrations
docker compose exec api alembic upgrade head

# Generate new migration after model changes
docker compose exec api alembic revision --autogenerate -m "description"
```

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://arlo_assistant:password@db:5432/arlo_assistant

# API
API_KEY=arlo-assistant-dev-key          # legacy dev auth key

# JWT
JWT_SECRET=your-random-secret-here      # CHANGE IN PRODUCTION
JWT_ACCESS_EXPIRY_MINUTES=30
JWT_REFRESH_EXPIRY_DAYS=7

# Claude
CLAUDE_CODE_OAUTH_TOKEN=                # from: claude setup-token
CLAUDE_MODEL=sonnet

# Environment
ENVIRONMENT=development                 # development | production
LOG_LEVEL=INFO
CORS_ORIGINS=*                          # comma-separated origins
```

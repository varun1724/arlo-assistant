# CLAUDE.md

## Project
Arlo Assistant is the personal AI assistant backend for the Arlo iOS app. It manages health, fitness, nutrition, tasks, goals, habits, recipes, knowledge, and reminders through conversational AI and direct API endpoints. This is the intelligence layer that powers the iOS app's voice-first, notification-driven experience.

## Tech Stack
- Python, FastAPI, async SQLAlchemy, Alembic
- PostgreSQL database, Docker Compose
- Conversational AI for voice intent parsing, planning, and recommendations

## Before Every Message
1. Read the memory index at `~/.claude/projects/-Users-varunscodingaccount-Desktop-Swift-projects-arlo-trading-engine/memory/MEMORY.md` for user context and prior decisions
2. Check the current plan file if one exists
3. Review git status and recent commits to understand current state

## Working Rules
- After completing any non-trivial code change, use a sub-agent (Explore type) to verify the changes compile, make sense architecturally, and don't break existing patterns before presenting results to the user
- Run syntax checks on every modified file before committing
- Run relevant tests locally when possible; if Docker is needed, provide the exact command
- Prefer editing existing files over creating new ones
- This backend serves the iOS app — API changes must maintain backward compatibility with the mobile client

## Relationship to Other Arlo Projects
- **Arlo (iOS app)**: The frontend client that consumes this backend's API
- **Arlo Runtime**: The workflow orchestration engine (separate concern — research pipelines, n8n automation)
- **Arlo Trading Engine**: The trading system (separate concern — no direct dependency)

## Deployment
Containers run on a Windows machine via Tailscale SSH (`ssh vsara@100.75.94`, project at `C:\trading\`). Deploy cycle: commit → push → SSH pull → docker compose build + up.

## What to Avoid
- Breaking mobile client API contracts
- Over-engineering AI agent systems before MVP validation
- Mixing runtime/trading concerns into the assistant
- Adding unnecessary complexity to the planner or memory systems

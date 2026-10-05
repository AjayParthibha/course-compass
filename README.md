# CourseCompass

An AI academic planner for Cornell CS students (Engineering and Arts & Sciences). Students see their degree as a prerequisite graph, edit it directly or ask an AI advisor for changes, and get course recommendations that fit their goals. A deterministic planner decides what's valid; the advisor (an OpenAI model) can only read the plan and propose changes for the student to approve.

CS 4701 project by Ajay Parthibha, Aryan Kumar and Mohit Soni.

## Moving parts

- **`web/`**: React frontend (graph, advisor chat, onboarding, explore, profile)
- **`backend/app/`**: FastAPI app
  - `planner/`: plan validation and requirement checks (the source of truth for what's allowed)
  - `advisor/`: LLM tool-use loop and the tools it can call (also served over MCP)
  - `catalog/`, `requirements/`: course data and degree rules
- **`data/`**: course snapshot from the Class Roster API and degree rules as YAML
- **`eval/`**: evaluation scenarios and runner

## Getting started

```bash
cp .env.example .env    # add your OPENAI_API_KEY
docker compose up
```

Open http://localhost:5173 and sign in with any code (e.g. `TEST-1`). Code changes reload automatically.

To work on the UI with sample data and a scripted advisor: `VITE_MOCK=1 docker compose up`.

# CourseCompass

An AI academic planner for Cornell CS students (Engineering and Arts & Sciences). Students see their degree as a prerequisite graph, edit it directly or ask an AI advisor for changes, and get course recommendations that fit their goals. A deterministic planner decides what's valid; the advisor (an OpenAI model) can only read the plan and propose changes for the student to approve.

CS 4701 project by Ajay Parthibha, Aryan Kumar and Mohit Soni.

## Moving parts

- **`web/`**: React frontend (graph, advisor chat, onboarding, explore, profile)
- **`backend/app/`**: FastAPI app
  - `planner/`: plan validation and requirement checks (the source of truth for what's allowed)
    - `solver/`: the CP-SAT model behind the exact audit and minimal-change plan repair
    - `recommend.py`: ranks a slot's eligible courses (and the external specialization's areas) by the student's profile and plan, with a reason for each point
    - `elicit.py`: decides whether a question is worth asking before recommending, by checking how much each likely answer would change the top picks
  - `advisor/`: LLM tool-use loop and the tools it can call (also served over MCP)
  - `catalog/`, `requirements/`: course data and degree rules
  - `onboarding.py`, `transcript.py`: reading pasted history and the unofficial transcript; `onboarding_model.py` asks the model about lines the regex can't read, choosing only among roster courses with that number, for the student to confirm
- **`data/`**: course snapshot from the Class Roster API and degree rules as YAML, by college and catalog year (Engineering and Arts & Sciences, 2023-24 and 2024-25). Each file names its sources and lists what it doesn't model in `notes`.
- **`eval/`**: evaluation scenarios and runner

## Evaluation

Scenarios are in `eval/scenarios.yaml` (both colleges) and `eval/advisor_scenarios.yaml`. Each one says what a student has taken, what they ask, and the expected outcome, with the reason in its notes.

```bash
cd eval
uv run python -m harness.run --mode validate       # baseline: apply the edit as asked, then check it
uv run python -m harness.run --mode repair_global  # the solver's minimal-change repair
uv run python -m harness.run --mode rebuild        # the same request, rebuilt from scratch
uv run python -m harness.run --mode elicit         # ask before recommending only when it matters
uv run python -m harness.run --mode elicit_fixed   # baseline: always ask (a fixed questionnaire)
uv run python -m harness.advisor --repeats 3       # the real advisor (needs OPENAI_API_KEY)
```

Each run writes a CSV to `eval/results/`.

## Getting started

```bash
cp .env.example .env    # add your OPENAI_API_KEY
docker compose up
```

Open http://localhost:5173 and sign in with any code (e.g. `TEST-1`). Code changes reload automatically.

To work on the UI with sample data and a scripted advisor: `VITE_MOCK=1 docker compose up`.

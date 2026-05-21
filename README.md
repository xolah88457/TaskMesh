# TaskMesh

A real-time multi-agent AI coding assistant powered by OpenCode Zen. Describe what you want to build, and a team of AI agents will plan, code, test, and document it — live in your browser.

---

## Before you start

You need three things installed on your computer:

- **Python 3.11 or newer** — check with `python3 --version` in your terminal
- **Node.js 18 or newer** — check with `node --version`
- **An OpenCode Zen API key** — get one at [opencode.ai/zen](https://opencode.ai/zen)

If you don't have Python or Node, install them first:
- Python: [python.org/downloads](https://www.python.org/downloads)
- Node.js: [nodejs.org](https://nodejs.org) (pick the LTS version)

---

## Setup (one time)

Open your terminal and run these commands in order.

### Step 1 — Clone the repo

```bash
git clone <this-repo> TaskMesh
cd TaskMesh
```

### Step 2 — Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### Step 3 — Configure environment

```bash
cp .env.example .env
# Edit .env — set your OpenCode Zen API key:
#   OPENCODE_GO_API_KEY=your-zen-key
# For local dev without a database or auth:
#   AUTH_DISABLED=true
```

### Step 4 — Install frontend dependencies

```bash
cd frontend
npm install
cp .env.local.example .env.local
# For local dev without auth:
#   VITE_AUTH_DISABLED=true
cd ..
```

---

## Running the app

You need **two terminals open at the same time** — one for the backend, one for the frontend.

### Terminal 1 — Start the backend

```bash
source venv/bin/activate
python3 -m uvicorn backend.main:socket_app --reload --port 8000
```

You should see: `Uvicorn running on http://0.0.0.0:8000`

> **CRITICAL:** use `socket_app` not `app` — the wrong entry point breaks all WebSockets.

### Terminal 2 — Start the frontend

```bash
cd frontend
npm run dev
```

You should see: `Local: http://localhost:5173`

### Open the app

Go to **[http://localhost:5173](http://localhost:5173)** in your browser.

With `AUTH_DISABLED=true` + `VITE_AUTH_DISABLED=true`, you go straight to the main app. No login, no billing gate.

---

## Adding your API key

You need an OpenCode Zen API key to make the agents work. Get one at [opencode.ai/zen](https://opencode.ai/zen).

Once you have it, add it as an environment variable:

```bash
export OPENCODE_GO_API_KEY=your-zen-key
```

Or add it to `.env`:

```
OPENCODE_GO_API_KEY=your-zen-key
```

You can also paste it in the app: click **⚙ Settings** → **OpenCode Zen API Key** → **Save & Apply**.

---

## Settings

Click **⚙** in the top-right to open the Settings panel.

| Section | What you can change |
|---|---|
| **Theme** | Default (matrix), Black, Tokyo Night, Light, Solarized |
| **Sprint** | The label shown in the header |
| **OpenCode Zen API Key** | Your master Zen API key |
| **Agents** | Add, remove, or customize any agent — 46 models across 3 tiers |

### Per-agent settings

Expand any agent row to configure it:

- **Role** — choose a preset role or set Custom
- **System Prompt** — the full instructions for that agent; edit freely
- **Model** — 46 models grouped by Flagship (Pro) / Balanced / Budget
- **Sampling** — Temperature, Top-P, Top-K sliders. Hit **✦ Recommended** to auto-fill suggested values
- Thinking budgets are disabled for now (will re-enable when provider support is confirmed)

Changes take effect on the next run. Config is saved to `agent-team.config.json`.

---

## Agent roles

| Role | What it does |
|---|---|
| **Manager** | Reads your brief, creates the task plan, coordinates the team |
| **WebDev** | Designs the overall architecture, API contracts, and data models |
| **Frontend** | Builds UI components, handles client-side state and API calls |
| **Backend** | Implements API endpoints, database logic, authentication |
| **Tester** | Writes tests and bug reports across the whole stack |
| **DevOps** | Handles Docker, CI/CD, deployment, and environment config |
| **Security** | Reviews for vulnerabilities, auth issues, and OWASP risks |
| **DataSci** | Owns data pipelines, analytics, and ML components |
| **Designer** | Defines UX specs, component states, and design system |
| **Docs** | Writes README, API docs, changelogs, and inline comments |
| **Logger** | Records everything that happens and produces a sprint summary |
| **Reviewer** | Reviews other agents' output and gives an APPROVED / NEEDS REVISION verdict |
| **Researcher** | Investigates the best approach before implementation starts |

---

## Troubleshooting

**Backend won't start**
- Make sure you're running from the TaskMesh folder and the venv is activated
- Try `pip install uvicorn` if you get `command not found`

**Frontend won't start**
- Run `npm install` inside the `frontend` folder first
- Make sure Node.js 18+ is installed (`node --version`)

**Agents do nothing / API errors**
- Check your OpenCode Zen API key is set in `.env` (`OPENCODE_GO_API_KEY`)
- Make sure the backend terminal is still running

**App shows blank or broken layout**
- Hard refresh the browser: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
- Make sure both the backend (port 8000) and frontend (port 5173) are running

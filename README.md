# Agent Team

A real-time multi-agent AI dashboard powered by NVIDIA NIM. Describe what you want to build, and a team of AI agents will plan, architect, code, test, and document it — live in your browser.

---

## Before you start

You need three things installed on your computer:

- **Python 3.9 or newer** — check with `python3 --version` in your terminal
- **Node.js 18 or newer** — check with `node --version`
- **A free NVIDIA NIM API key** — get one at [build.nvidia.com/settings/api-keys](https://build.nvidia.com/settings/api-keys) (free account, no credit card)

If you don't have Python or Node, install them first:
- Python: [python.org/downloads](https://www.python.org/downloads)
- Node.js: [nodejs.org](https://nodejs.org) (pick the LTS version)

---

## Setup (one time)

Open your terminal and run these commands in order.

### Step 1 — Download the repo

```bash
git clone <this-repo> AgentTeam
cd AgentTeam
```

### Step 2 — Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

> If `pip` isn't found, try `pip3` instead.

### Step 3 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running the app

You need **two terminals open at the same time** — one for the backend, one for the frontend.

### Terminal 1 — Start the backend

```bash
cd AgentTeam
python3 -m uvicorn backend.main:socket_app --reload --port 8000
```

You should see: `Uvicorn running on http://0.0.0.0:8000`

> If you get `command not found: uvicorn`, run `pip install uvicorn` then try again.
> If you get `command not found: python3`, try `python` instead of `python3`.

### Terminal 2 — Start the frontend

```bash
cd AgentTeam/frontend
npm run dev
```

You should see: `Local: http://localhost:5173`

### Step 3 — Open the app

Go to **[http://localhost:5173](http://localhost:5173)** in your browser.

---

## Adding your API key

You need a free NVIDIA NIM API key to make the agents work. Get one at [build.nvidia.com/settings/api-keys](https://build.nvidia.com/settings/api-keys).

Once you have it, add it in the app:

1. Click the **⚙** icon in the top-right corner
2. Paste your key (starts with `nvapi-`) into the **NVIDIA NIM** field
3. Click **Save & Apply**

Alternatively, set it as an environment variable before starting the backend:

```bash
export NVIDIA_API_KEY=nvapi-your-key-here
```

---

## Using a different project folder

By default, agents work inside the AgentTeam folder itself. To point them at **your own project**, add `PROJECT_DIR=` before the backend start command:

```bash
PROJECT_DIR=/Users/you/Projects/MyApp python3 -m uvicorn backend.main:socket_app --reload --port 8000
```

Replace `/Users/you/Projects/MyApp` with the actual path to your project folder. Everything else stays the same. The agents will read/write files there, and your AgentTeam folder won't be touched.

**How to find your project's path:**
- On Mac: drag the folder into the terminal window and it will paste the path
- Or `cd` into your project folder and run `pwd` to print it

---

## Running a task

1. Type what you want to build in the input at the top (e.g. *"Add user login with JWT auth"*)
2. Press **Enter** or click **▶ Start**
3. Watch the agents plan and work in real time

The **Manager** agent reads your brief, names the feature, and assigns tasks to each worker agent. Workers run at the same time — each using their own model and role instructions. You can watch their status, messages, and terminal output live.

---

## Settings

Click **⚙** in the top-right to open the Settings panel.

| Section | What you can change |
|---|---|
| **Theme** | Default (matrix), Black, Tokyo Night, Light, Solarized |
| **Sprint** | The label shown in the header |
| **NVIDIA API Key** | Your `nvapi-` key |
| **Agents** | Add, remove, or customize any agent |

### Per-agent settings

Expand any agent row to configure it:

- **Role** — choose a preset role (see list below) or set Custom
- **System Prompt** — the full instructions for that agent; edit freely
- **Model** — 40+ models grouped by Flagship / Balanced / Fast / Code
- **Sampling** — Temperature, Top-P, Top-K sliders. Hit **✦ Recommended** to auto-fill the model creator's suggested values
- **Thinking** — on supported models, a slider from Off to Max that controls how many tokens the model spends reasoning before answering

Changes take effect on the next run. Config is saved to `agent-team.config.json` in your project folder.

---

## Agent roles

| Role | What it does |
|---|---|
| **Manager** | Reads your brief, names the feature, assigns tasks to everyone else |
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

## Thinking-capable models

These models support extended reasoning. When selected, a **Thinking** slider appears in the agent settings (Off → Low → Med → High → X-Hi → Max):

| Model | Max thinking tokens |
|---|---|
| Qwen3 Coder 480B | 38,912 |
| Qwen3.5 397B | 38,912 |
| Qwen3.5 122B / Qwen3 80B | 32,768 |
| DeepSeek V4 Pro / Kimi K2.6 / MiniMax M2.7 | 32,768 |
| DeepSeek V4 Flash / Gemma 4 31B | 16,384 |

---

## Troubleshooting

**Backend won't start**
- Make sure you're running the command from inside the `AgentTeam` folder
- Try `pip install uvicorn` if you get `command not found`
- Try `python` instead of `python3` if Python isn't found

**Frontend won't start**
- Run `npm install` inside the `frontend` folder first
- Make sure Node.js 18+ is installed (`node --version`)

**Agents do nothing / API errors**
- Check your API key is entered correctly in Settings (starts with `nvapi-`)
- Make sure the backend terminal is still running
- Try a smaller/faster model like `meta/llama-3.1-8b-instruct` to test

**App shows blank or broken layout**
- Hard refresh the browser: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
- Make sure both the backend (port 8000) and frontend (port 5173) are running

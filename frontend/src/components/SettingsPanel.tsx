import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { THEMES } from '../themes'
import { useAuthFetch } from '../hooks/useAuthFetch'

interface AgentCfg {
  id: string
  name: string
  role: string
  model: string
  temperature: number
  top_p: number
  top_k: number
  thinking_budget: number
  planner: boolean
  color: string
  icon: string
  system_prompt?: string
}

// Models that support thinking — matches backend THINKING_MODEL_IDS + ANTHROPIC_THINKING_MODEL_IDS.
// Slider is disabled for models NOT in this set.
const THINKING_CAPABLE_MODELS: Set<string> = new Set([
  'kimi-k2.5','kimi-k2.6',
  'qwen3.5-plus','qwen3.6-plus',
  'minimax-m2.7','minimax-m2.5','minimax-m2.5-free',
  'mimo-v2.5-pro','mimo-v2.5',
  'glm-5','glm-5.1',
  'deepseek-v4-pro','deepseek-v4-flash','deepseek-v4-flash-free',
  'claude-haiku-4-5','claude-opus-4-1','claude-opus-4-5','claude-opus-4-6','claude-opus-4-7',
  'claude-sonnet-4','claude-sonnet-4-5','claude-sonnet-4-6',
])

interface AgentPreset {
  id: string
  name: string
  role: string
  icon: string
  color: string
  planner: boolean
  prompt: string
}

// Presets split by phase for optgroup rendering
const PLANNER_PRESETS: AgentPreset[] = [
  {
    id: 'webdev',
    name: 'WebDev',
    role: 'Architect',
    icon: '🏗',
    color: '#8b5cf6',
    planner: true,
    prompt: `You are the WebDev (Full-Stack Architect) agent in a software development team.

You run in Phase 1 — before any implementation begins. Your job is to design the technical architecture so that all executor agents start from a solid, agreed spec.

Responsibilities:
- Define the project/module structure and folder layout
- Design data models and database schema
- Specify API endpoint contracts (method, path, request/response shapes)
- Choose appropriate libraries and frameworks
- Identify shared types and interfaces that Frontend and Backend will use

Output: A concise technical spec using bullet points and inline code snippets. Focus on decisions and contracts, not implementation details. Keep your response under 300 words.

Your spec will be submitted to the Manager and shared with all executor agents as planning context.`,
  },
  {
    id: 'devops',
    name: 'DevOps',
    role: 'Infrastructure',
    icon: '🚀',
    color: '#06b6d4',
    planner: true,
    prompt: `You are the DevOps (Infrastructure Engineer) agent in a software development team.

You run in Phase 1 — before any implementation begins. Your job is to design the deployment and infrastructure plan so that executor agents know the environment they're building for.

Responsibilities:
- Plan Docker/container strategy and docker-compose structure
- Design CI/CD pipeline (GitHub Actions, GitLab CI, or equivalent)
- Define environment variables, secrets management, and config strategy
- Plan monitoring, log aggregation, and health check approach
- Identify any infrastructure constraints that affect Backend or Frontend implementation

Boundaries:
- Do NOT write application logic or UI code
- Always use environment variables for secrets — never hardcode them

Output: An infrastructure plan with key config structure (YAML, shell). Flag any constraints executor agents must respect. Under 250 words.

Your spec will be submitted to the Manager and shared with all executor agents as planning context.`,
  },
  {
    id: 'designer',
    name: 'Designer',
    role: 'UX',
    icon: '🎯',
    color: '#ec4899',
    planner: true,
    prompt: `You are the Designer (UX Designer) agent in a software development team.

You run in Phase 1 — before any implementation begins. Your job is to define the user experience and component specs so that Frontend has a clear blueprint to implement.

Responsibilities:
- Define component hierarchy and page/screen layouts
- Specify the design system: colors, typography, spacing, component variants
- Describe user flows for key journeys (happy path and error states)
- Specify interactive states for each component: default, hover, focus, active, disabled, loading, error, empty
- Ensure WCAG 2.1 AA accessibility compliance

For each component, specify:
  Name: [ComponentName]
  Purpose: [what it does]
  Layout: [description]
  States: [list]
  Props/variants: [key options]

Output: Structured component specs using bullet lists, not paragraphs. Under 300 words.

Your spec will be submitted to the Manager and shared with all executor agents as planning context.`,
  },
  {
    id: 'researcher',
    name: 'Researcher',
    role: 'Tech Lead',
    icon: '🧠',
    color: '#67e8f9',
    planner: true,
    prompt: `You are the Researcher (Technical Lead) agent in a software development team.

You run in Phase 1 — before any implementation begins. Your job is to investigate the best approach for the feature so that other agents start with a solid foundation rather than guessing.

Responsibilities:
- Evaluate technology choices: libraries, frameworks, algorithms, patterns
- Compare approaches with clear trade-off analysis (performance, complexity, maintenance)
- Identify potential pitfalls, known issues, or compatibility concerns with the current stack
- Research relevant best practices and industry standards for the problem domain
- Provide concrete, actionable recommendations — not just options

Output format:
  ## Research: [Feature Name]
  **Recommendation:** [one clear recommendation]
  **Rationale:** [2-3 sentences]
  **Trade-offs:**
  - Option A: [pros / cons]
  - Option B: [pros / cons]
  **Risks to watch:** [bullet list]

Output: The formatted research report. Be decisive — a clear recommendation is more valuable than a balanced "it depends." Under 350 words.

Your report will be submitted to the Manager and shared with all executor agents as planning context.`,
  },
]

const EXECUTOR_PRESETS: AgentPreset[] = [
  {
    id: 'frontend',
    name: 'Frontend',
    role: 'UI/UX',
    icon: '🎨',
    color: '#22c55e',
    planner: false,
    prompt: `You are the Frontend (UI Engineer) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1 (architecture, design, research). Use that context to guide your implementation.

Responsibilities:
- Build responsive, accessible UI components (React/Vue/HTML)
- Implement client-side routing and state management
- Connect to backend APIs via fetch/axios using the agreed contract
- Handle loading, error, empty, and success states in the UI
- Follow the design spec and architecture doc from Phase 1 planners

Boundaries:
- Do NOT touch server-side code, database queries, or deployment configs
- Use only the API endpoints defined by WebDev or Backend — do not invent new ones
- Prioritize accessibility: ARIA roles, keyboard navigation, color contrast

Output: Write every component, hook, and style file using [FILE: path][/FILE] blocks. Then one short paragraph summarising what you built.`,
  },
  {
    id: 'backend',
    name: 'Backend',
    role: 'API',
    icon: '⚙️',
    color: '#f97316',
    planner: false,
    prompt: `You are the Backend (API Engineer) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1 (architecture, infrastructure, research). Use that context to guide your implementation.

Responsibilities:
- Implement REST or GraphQL API endpoints (routes, controllers, middleware)
- Write database queries, ORM models, and migrations
- Handle authentication, authorization, and input validation
- Implement core business logic and service layers
- Write server-side error handling and logging

Boundaries:
- Do NOT touch frontend components or CSS
- Always validate and sanitize all user input
- Use environment variables for secrets — never hardcode credentials
- Follow the API contract defined by WebDev in Phase 1

Output: Write every endpoint, model, migration, and helper file using [FILE: path][/FILE] blocks. Then one short paragraph listing the endpoints you implemented.`,
  },
  {
    id: 'tester',
    name: 'Tester',
    role: 'QA',
    icon: '🧪',
    color: '#ef4444',
    planner: false,
    prompt: `You are the Tester (QA Engineer) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Use those specs to understand what was planned and write tests that verify the implementation matches them.

Responsibilities:
- Write unit tests for individual functions and components
- Write integration tests for API endpoints and database interactions
- Write end-to-end tests for critical user journeys
- Review code for logic errors, edge cases, and security issues
- Create bug reports with clear reproduction steps

Test strategy:
- Test the happy path first, then edge cases (empty input, invalid types, boundary values)
- Mock external services in unit tests; use a real test DB in integration tests
- Target full coverage of critical business logic code paths

Output: Write every test file using [FILE: path][/FILE] blocks. Then one short paragraph listing bugs found with severity.`,
  },
  {
    id: 'security',
    name: 'Security',
    role: 'Auditor',
    icon: '🔬',
    color: '#a855f7',
    planner: false,
    prompt: `You are the Security (Security Auditor) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Use those specs to understand the intended architecture and review the implementation against security best practices.

Responsibilities:
- Check for OWASP Top 10 vulnerabilities: SQL injection, XSS, CSRF, broken auth, broken access control
- Review authentication and authorization logic for flaws
- Verify all user input is validated and sanitized
- Check for exposed secrets or insecure configurations
- Assess API security: rate limiting, CORS policy, JWT handling
- Flag insecure or outdated dependencies

For each finding, report:
  Severity: Critical / High / Medium / Low
  Location: [module or endpoint]
  Issue: [description]
  Fix: [recommended remediation]

Output: Write a [FILE: security-audit.md][/FILE] report with every finding. Then list critical/high findings inline for the Manager.`,
  },
  {
    id: 'datasci',
    name: 'DataSci',
    role: 'Analyst',
    icon: '📊',
    color: '#14b8a6',
    planner: false,
    prompt: `You are the DataSci (Data Scientist / Analyst) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Use that context to implement data-intensive features that fit the agreed architecture.

Responsibilities:
- Design data collection strategy and storage schema
- Write data transformation, aggregation, and ETL pipelines
- Implement analytics endpoints or background jobs
- Define key metrics and how to calculate them
- Build or integrate ML models where the feature requires it

Boundaries:
- Do NOT build UI components — expose data through API endpoints that Frontend consumes
- Document data schemas and pipeline dependencies clearly

Output: Write every data model, pipeline, and analytics file using [FILE: path][/FILE] blocks. Then one short paragraph describing the schema decisions.`,
  },
  {
    id: 'docs',
    name: 'Docs',
    role: 'Writer',
    icon: '📝',
    color: '#84cc16',
    planner: false,
    prompt: `You are the Docs (Technical Writer) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Use those specs to produce accurate documentation that reflects what was planned and built.

Responsibilities:
- Write or update the README (setup, usage, architecture overview)
- Document all API endpoints: method, path, parameters, request/response examples
- Write JSDoc or docstring comments for public functions and classes
- Create user-facing feature guides and changelog entries

Quality standards:
- Every public endpoint and exported function must be documented
- All code examples must be valid and runnable
- Write for a developer new to the project — avoid unexplained jargon

Output: Write every doc file (README.md, api.md, changelog, etc.) using [FILE: path][/FILE] blocks. Write the full content of each file — do not summarise.`,
  },
  {
    id: 'logger',
    name: 'Logger',
    role: 'Chronicler',
    icon: '🪵',
    color: '#f59e0b',
    planner: false,
    prompt: `You are the Logger (Chronicler) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Your job is to observe, record, and summarize everything that happens during this sprint. You are the single source of truth for what was done, why, and by whom.

Responsibilities:
- Log every significant action taken by each agent: what they were asked to do, what they decided, and what they produced
- Record key decisions and the reasoning behind them
- Note any errors, blockers, retries, or unexpected outcomes
- Track task status transitions (assigned → in progress → complete / blocked)
- Flag inconsistencies between agents (e.g. Frontend consuming an endpoint Backend hasn't built yet)
- Produce a clean, structured run summary at the end

Log format for each event:
  [AGENT] [ACTION] — [DETAILS]
  e.g. [BACKEND] COMPLETED endpoint POST /auth/login — returns { token, user }
  e.g. [TESTER]  BLOCKED waiting on Frontend component LoginForm
  e.g. [MANAGER] DECISION — chose REST over GraphQL for simplicity

End-of-run summary format:
  ## Sprint Summary
  - Feature: [name]
  - Agents active: [list]
  - Tasks completed: N / N
  - Key decisions: [bullet list]
  - Issues encountered: [bullet list or "None"]
  - Artifacts produced: [bullet list]

Output: Write a [FILE: sprint-log.md][/FILE] containing the full structured log and Sprint Summary. Also echo the Sprint Summary inline for the Manager.`,
  },
  {
    id: 'reviewer',
    name: 'Reviewer',
    role: 'Code Review',
    icon: '🔍',
    color: '#e879f9',
    planner: false,
    prompt: `You are the Reviewer (Code Reviewer) agent in a software development team.

You run in the execution phase. You will receive your task from the Manager along with planning specs from Phase 1. Use those specs as the reference standard — check whether implementations match what was planned.

Responsibilities:
- Review Frontend code for component structure, state management correctness, and accessibility
- Review Backend code for logic errors, missing validation, and API contract adherence
- Check that implementations match the architecture spec defined by WebDev in Phase 1
- Verify Tester coverage is adequate for the implemented functionality
- Identify dead code, duplicate logic, or overcomplicated solutions
- Ensure naming conventions and code style are consistent across the codebase

Review checklist:
  □ Does the implementation match the task spec?
  □ Are edge cases handled (empty input, errors, auth failures)?
  □ Is there any duplicated or unnecessary code?
  □ Are all external inputs validated?
  □ Does it follow the project's established patterns?

For each issue found, report:
  Severity: Blocker / Major / Minor / Nit
  File/Module: [location]
  Issue: [description]
  Fix: [suggested change]

Output: Write a [FILE: review-report.md][/FILE] containing the full structured review grouped by agent/module. End with overall verdict: APPROVED / APPROVED WITH NOTES / NEEDS REVISION. Also echo the verdict inline.`,
  },
]

const MANAGER_PRESET: AgentPreset = {
  id: 'manager',
  name: 'Manager',
  role: 'Coordinator',
  icon: '👔',
  color: '#6366f1',
  planner: false,
  prompt: '',  // auto-generated by build_manager_system — not editable
}

const AGENT_PRESETS: AgentPreset[] = [MANAGER_PRESET, ...PLANNER_PRESETS, ...EXECUTOR_PRESETS]

interface Config {
  sprint: string
  provider: { name: string; baseURL: string; apiKey: string }
  agents: AgentCfg[]
}

const MODEL_GROUPS = [
  {
    label: 'Flagship (Pro)',
    models: [
      { id: 'deepseek-v4-pro',   label: 'DeepSeek V4 Pro' },
      { id: 'glm-5.1',           label: 'GLM-5.1' },
      { id: 'kimi-k2.6',         label: 'Kimi K2.6' },
      { id: 'mimo-v2.5-pro',     label: 'MiMo V2.5 Pro' },
      { id: 'minimax-m2.7',      label: 'MiniMax M2.7' },
      { id: 'qwen3.6-plus',      label: 'Qwen3.6 Plus' },
      { id: 'claude-opus-4-1',   label: 'Claude Opus 4.1' },
      { id: 'claude-opus-4-5',   label: 'Claude Opus 4.5' },
      { id: 'claude-opus-4-6',   label: 'Claude Opus 4.6' },
      { id: 'claude-opus-4-7',   label: 'Claude Opus 4.7' },
      { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
      { id: 'gpt-5.4-pro',       label: 'GPT-5.4 Pro' },
      { id: 'gpt-5.5-pro',       label: 'GPT-5.5 Pro' },
      { id: 'gpt-5.5',           label: 'GPT-5.5' },
      { id: 'gpt-5.4',           label: 'GPT-5.4' },
      { id: 'gemini-3.1-pro',    label: 'Gemini 3.1 Pro' },
    ],
  },
  {
    label: 'Balanced',
    models: [
      { id: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
      { id: 'glm-5',             label: 'GLM-5' },
      { id: 'kimi-k2.5',         label: 'Kimi K2.5' },
      { id: 'mimo-v2.5',         label: 'MiMo V2.5' },
      { id: 'minimax-m2.5',      label: 'MiniMax M2.5' },
      { id: 'qwen3.5-plus',      label: 'Qwen3.5 Plus' },
      { id: 'claude-sonnet-4',   label: 'Claude Sonnet 4' },
      { id: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5' },
      { id: 'claude-haiku-4-5',  label: 'Claude Haiku 4.5' },
      { id: 'gpt-5',             label: 'GPT-5' },
      { id: 'gpt-5.1',           label: 'GPT-5.1' },
      { id: 'gpt-5.2',           label: 'GPT-5.2' },
      { id: 'gpt-5-codex',       label: 'GPT-5 Codex' },
      { id: 'gpt-5.1-codex',     label: 'GPT-5.1 Codex' },
      { id: 'gpt-5.1-codex-max', label: 'GPT-5.1 Codex Max' },
      { id: 'gpt-5.2-codex',     label: 'GPT-5.2 Codex' },
      { id: 'gpt-5.3-codex',     label: 'GPT-5.3 Codex' },
      { id: 'gpt-5.1-codex-mini',label: 'GPT-5.1 Codex Mini' },
      { id: 'gpt-5.3-codex-spark',label:'GPT-5.3 Codex Spark' },
      { id: 'gpt-5.4-mini',      label: 'GPT-5.4 Mini' },
      { id: 'gemini-3-flash',    label: 'Gemini 3 Flash' },
      { id: 'gemini-3.5-flash',  label: 'Gemini 3.5 Flash' },
    ],
  },
  {
    label: 'Budget',
    models: [
      { id: 'nemotron-3-super',       label: 'Nemotron 3 Super' },
      { id: 'deepseek-v4-flash-free', label: 'DeepSeek V4 Flash (Budget)' },
      { id: 'big-pickle',             label: 'Big Pickle' },
      { id: 'nemotron-3-super-free',  label: 'Nemotron 3 Super (Budget)' },
      { id: 'minimax-m2.5-free',      label: 'MiniMax M2.5 (Budget)' },
      { id: 'gpt-5-nano',             label: 'GPT-5 Nano' },
      { id: 'gpt-5.4-nano',           label: 'GPT-5.4 Nano' },
      { id: 'grok-build-0-1',         label: 'Grok Build 0-1' },
    ],
  },
]

const KNOWN_MODELS = MODEL_GROUPS.flatMap(g => g.models)

const ICONS = ['👔','🏗','🎨','⚙️','🧪','🔬','📊','🎯','🚀','💡','🔧','📝','🤖','👾','🧠','🦾']

interface Rec { temperature: number; top_p: number; top_k?: number; note?: string; thinking_budget?: number }

const MODEL_RECOMMENDATIONS: Record<string, Rec> = {
  // ── DeepSeek ────────────────────────────────────────────────
  'deepseek-v4-pro':       { temperature: 0.3, top_p: 0.95, thinking_budget: 2048, note: 'API scales internally' },
  'deepseek-v4-flash':     { temperature: 0.3, top_p: 0.95, note: 'API scales internally' },
  'deepseek-v4-flash-free':{ temperature: 0.3, top_p: 0.95, note: 'API scales internally' },
  // ── GLM ─────────────────────────────────────────────────────
  'glm-5.1':               { temperature: 0.7, top_p: 0.95, thinking_budget: 1024 },
  'glm-5':                 { temperature: 0.7, top_p: 0.95 },
  // ── Kimi ────────────────────────────────────────────────────
  'kimi-k2.6':             { temperature: 0.6, top_p: 0.9, thinking_budget: 4096 },
  'kimi-k2.5':             { temperature: 0.6, top_p: 0.9, thinking_budget: 4096 },
  // ── MiMo ────────────────────────────────────────────────────
  'mimo-v2.5-pro':         { temperature: 0.7, top_p: 0.95, thinking_budget: 2048 },
  'mimo-v2.5':             { temperature: 0.7, top_p: 0.95 },
  // ── MiniMax ─────────────────────────────────────────────────
  'minimax-m2.7':          { temperature: 0.7, top_p: 0.9, thinking_budget: 4096 },
  'minimax-m2.5':          { temperature: 0.7, top_p: 0.9 },
  'minimax-m2.5-free':     { temperature: 0.7, top_p: 0.9 },
  // ── Qwen ────────────────────────────────────────────────────
  'qwen3.6-plus':          { temperature: 0.6, top_p: 0.95, top_k: 20, thinking_budget: 1024 },
  'qwen3.5-plus':          { temperature: 0.6, top_p: 0.95, top_k: 20 },
  // ── Nemotron ────────────────────────────────────────────────
  'nemotron-3-super':      { temperature: 0.6, top_p: 0.9 },
  'nemotron-3-super-free': { temperature: 0.6, top_p: 0.9 },
  // ── Big Pickle ──────────────────────────────────────────────
  'big-pickle':            { temperature: 0.7, top_p: 0.95 },
  // ── Claude ──────────────────────────────────────────────────
  'claude-haiku-4-5':      { temperature: 0.7, top_p: 0.9, thinking_budget: 2048 },
  'claude-opus-4-1':       { temperature: 0.7, top_p: 0.9, thinking_budget: 8192 },
  'claude-opus-4-5':       { temperature: 0.7, top_p: 0.9, thinking_budget: 8192 },
  'claude-opus-4-6':       { temperature: 0.7, top_p: 0.9, thinking_budget: 8192 },
  'claude-opus-4-7':       { temperature: 0.7, top_p: 0.9, thinking_budget: 8192 },
  'claude-sonnet-4':       { temperature: 0.7, top_p: 0.9, thinking_budget: 4096 },
  'claude-sonnet-4-5':     { temperature: 0.7, top_p: 0.9, thinking_budget: 4096 },
  'claude-sonnet-4-6':     { temperature: 0.7, top_p: 0.9, thinking_budget: 4096 },
  // ── GPT ─────────────────────────────────────────────────────
  'gpt-5':                 { temperature: 0.7, top_p: 1.0 },
  'gpt-5-codex':           { temperature: 0.5, top_p: 0.9 },
  'gpt-5-nano':            { temperature: 0.7, top_p: 1.0 },
  'gpt-5.1':               { temperature: 0.7, top_p: 1.0 },
  'gpt-5.1-codex':         { temperature: 0.5, top_p: 0.9 },
  'gpt-5.1-codex-max':     { temperature: 0.5, top_p: 0.9 },
  'gpt-5.1-codex-mini':    { temperature: 0.5, top_p: 0.9 },
  'gpt-5.2':               { temperature: 0.7, top_p: 1.0 },
  'gpt-5.2-codex':         { temperature: 0.5, top_p: 0.9 },
  'gpt-5.3-codex':         { temperature: 0.5, top_p: 0.9 },
  'gpt-5.3-codex-spark':   { temperature: 0.5, top_p: 0.9 },
  'gpt-5.4':               { temperature: 0.7, top_p: 1.0 },
  'gpt-5.4-mini':          { temperature: 0.7, top_p: 1.0 },
  'gpt-5.4-nano':          { temperature: 0.7, top_p: 1.0 },
  'gpt-5.4-pro':           { temperature: 0.7, top_p: 1.0 },
  'gpt-5.5':               { temperature: 0.7, top_p: 1.0 },
  'gpt-5.5-pro':           { temperature: 0.5, top_p: 1.0 },
  // ── Gemini ──────────────────────────────────────────────────
  'gemini-3-flash':        { temperature: 1.0, top_p: 0.96, top_k: 64 },
  'gemini-3.1-pro':        { temperature: 0.7, top_p: 0.95 },
  'gemini-3.5-flash':      { temperature: 1.0, top_p: 0.96, top_k: 64 },
  // ── Grok ────────────────────────────────────────────────────
  'grok-build-0-1':        { temperature: 0.7, top_p: 0.95 },
}

function defaultAgent(presetId: string, model: string, overrides: Partial<AgentCfg> = {}): AgentCfg {
  const p = AGENT_PRESETS.find(x => x.id === presetId)!
  return {
    id: p.id, name: p.name, role: p.role, icon: p.icon, color: p.color,
    model, temperature: 0.6, top_p: 0.9, top_k: 0, thinking_budget: 0,
    planner: p.planner, system_prompt: p.prompt,
    ...overrides,
  }
}

// Default config — manager only. Users add executors via +Add or Recommended Layout.
const DEFAULT_CONFIG: Config = {
  sprint: 'Sprint #1',
  provider: { name: 'OpenCode Zen', baseURL: 'https://opencode.ai/zen/v1', apiKey: '' },
  agents: [
    defaultAgent('manager', 'deepseek-v4-pro'),
  ],
}

// Recommended agent-to-model mapping — applied by the "Recommended layout" button.
const RECOMMENDED_LAYOUT: { roleId: string; model: string; temperature?: number; top_p?: number; thinking_budget?: number }[] = [
  { roleId: 'manager',    model: 'deepseek-v4-pro',                                       thinking_budget: 0 },
  { roleId: 'webdev',     model: 'kimi-k2.6',                                             thinking_budget: 4096 },
  { roleId: 'researcher', model: 'kimi-k2.5',                                             thinking_budget: 4096 },
  { roleId: 'backend',    model: 'deepseek-v4-flash',   temperature: 0.5, top_p: 0.85,    thinking_budget: 0 },
  { roleId: 'frontend',   model: 'mimo-v2.5',                                             thinking_budget: 0 },
  { roleId: 'tester',     model: 'qwen3.5-plus',        temperature: 0.5,                 thinking_budget: 1024 },
  { roleId: 'docs',       model: 'qwen3.5-plus',        temperature: 0.4,                 thinking_budget: 0 },
  { roleId: 'logger',     model: 'qwen3.5-plus',        temperature: 0.3,                 thinking_budget: 0 },
  { roleId: 'reviewer',   model: 'deepseek-v4-pro',                                       thinking_budget: 2048 },
]

function Slider({ label, value, min, max, step, disabled, onChange }: {
  label: string; value: number; min: number; max: number; step: number; disabled?: boolean
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono w-12 shrink-0" style={{ color: 'var(--c-text-3)' }}>{label}</span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        disabled={disabled}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1 cursor-pointer"
        style={{ accentColor: 'var(--c-accent)', opacity: disabled ? 0.4 : 1 }}
      />
      <span className="text-[10px] font-mono w-8 text-right tabular-nums" style={{ color: 'var(--c-text-2)' }}>{value}</span>
    </div>
  )
}

interface Props {
  open: boolean
  onClose: () => void
  onSaved: (agents: AgentCfg[]) => void
  themeId: string
  onThemeChange: (id: string) => void
  initialTab?: 'project' | 'account'
}

export default function SettingsPanel({ open, onClose, onSaved, themeId, onThemeChange, initialTab = 'project' }: Props) {
  const [cfg, setCfg] = useState<Config>(DEFAULT_CONFIG)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [showRecConfirm, setShowRecConfirm] = useState(false)
  const [recMsg, setRecMsg] = useState('')
  const [activeTab, setActiveTab] = useState<'project' | 'account'>(initialTab)
  const authFetch = useAuthFetch()
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    authFetch('/api/config')
      .then(r => r.json())
      .then(data => setCfg({
        sprint:   data.sprint   ?? 'Sprint #1',
        provider: { name: 'OpenCode Zen', baseURL: 'https://opencode.ai/zen/v1', ...data.provider },
        agents:   (data.agents ?? []).map((a: AgentCfg) => {
          const preset = AGENT_PRESETS.find(p => p.id === a.id)
          return {
            ...{ temperature: 0.7, top_p: 0.9, top_k: 0, thinking_budget: 0 },
            ...{ planner: preset?.planner ?? false, system_prompt: preset?.prompt ?? '' },
            ...a,
          }
        }),
      }))
      .catch(() => {})
  }, [open])

  const updateProvider = (key: keyof Config['provider'], val: string) =>
    setCfg(c => ({ ...c, provider: { ...c.provider, [key]: val } }))

  const updateAgent = (idx: number, key: keyof AgentCfg, val: string | number | boolean) =>
    setCfg(c => {
      const agents = c.agents.map((a, i) => i === idx ? { ...a, [key]: val } : a)
      return { ...c, agents }
    })

  const applyAgentPreset = (idx: number, fields: Partial<AgentCfg>) =>
    setCfg(c => ({
      ...c,
      agents: c.agents.map((a, i) => i === idx ? { ...a, ...fields } : a),
    }))

  const addAgent = () => {
    const usedIds = new Set(cfg.agents.map(a => a.id))
    const next = AGENT_PRESETS.find(p => p.id !== 'manager' && !usedIds.has(p.id))
    const newAgent: AgentCfg = next
      ? defaultAgent(next.id, 'deepseek-v4-flash')
      : {
          id: `agent${cfg.agents.length + 1}`,
          name: 'Agent', role: 'Specialist',
          model: 'deepseek-v4-flash',
          temperature: 0.7, top_p: 0.9, top_k: 0, thinking_budget: 0,
          planner: false, color: '#6b7280', icon: '🤖', system_prompt: '',
        }
    setCfg(c => ({ ...c, agents: [...c.agents, newAgent] }))
  }

  const removeAgent = (idx: number) =>
    setCfg(c => ({ ...c, agents: c.agents.filter((_, i) => i !== idx) }))

  const applyRecommendedLayout = () => {
    setRecMsg('')
    // Warn if no API key configured
    if (!cfg.provider.apiKey.trim()) {
      setRecMsg('Warning: No API key is set. Agents will fail to run until a valid OpenCode Zen key is provided.')
    }
    const newAgents = RECOMMENDED_LAYOUT.map(r => defaultAgent(r.roleId as AgentPreset['id'], r.model, {
      ...(r.temperature !== undefined ? { temperature: r.temperature } : {}),
      ...(r.top_p !== undefined ? { top_p: r.top_p } : {}),
      ...(r.thinking_budget !== undefined ? { thinking_budget: r.thinking_budget } : {}),
    }))
    setCfg(c => ({ ...c, agents: newAgents }))
    setShowRecConfirm(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await authFetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      setSaved(true)
      onSaved(cfg.agents)
      setTimeout(() => { setSaved(false); onClose() }, 800)
    } catch {
      alert('Failed to save config — is the backend running?')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop (z-40) behind panel (z-50) */}
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40"
            style={{ background: 'rgba(0,0,0,0.55)' }}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            key="panel"
            className="fixed right-0 top-0 h-full w-[480px] z-50 flex flex-col overflow-hidden"
            style={{ background: 'var(--c-bg)', borderLeft: '1px solid var(--c-border)' }}
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 shrink-0" style={{ borderBottom: '1px solid var(--c-border)' }}>
            <div className="flex items-center gap-2">
              <span className="text-sm" style={{ color: 'var(--c-text-2)' }}>⚙</span>
              <span className="text-xs font-mono font-semibold tracking-widest uppercase" style={{ color: 'var(--c-text-1)' }}>Settings</span>
            </div>
            <button onClick={onClose} className="text-lg leading-none" style={{ color: 'var(--c-text-3)' }}>×</button>
          </div>

          {/* Tab bar */}
          <div className="flex shrink-0" style={{ borderBottom: '1px solid var(--c-border)' }}>
            <button
              onClick={() => setActiveTab('project')}
              className="flex-1 text-[10px] font-mono py-2 tracking-widest uppercase transition-colors"
              style={{ color: activeTab === 'project' ? 'var(--c-accent)' : 'var(--c-text-3)', borderBottom: activeTab === 'project' ? '1px solid var(--c-accent)' : '1px solid transparent' }}
            >
              Project Settings
            </button>
            <button
              onClick={() => setActiveTab('account')}
              className="flex-1 text-[10px] font-mono py-2 tracking-widest uppercase transition-colors"
              style={{ color: activeTab === 'account' ? 'var(--c-accent)' : 'var(--c-text-3)', borderBottom: activeTab === 'account' ? '1px solid var(--c-accent)' : '1px solid transparent' }}
            >
              Settings
            </button>
          </div>

          {/* Scrollable body */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">

            <AnimatePresence mode="wait">
            {activeTab === 'project' ? (
              <>
            {/* Sprint */}
            <Section title="Project">
              <Field label="Sprint">
                <input
                  className={inputCls}
                  style={inputStyle()}
                  value={cfg.sprint}
                  onChange={e => setCfg(c => ({ ...c, sprint: e.target.value }))}
                  placeholder="Sprint #1"
                />
              </Field>
            </Section>

            {/* Agents */}
            <Section title="Agents" action={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowRecConfirm(true)}
                  className="text-[10px] font-mono px-2 py-0.5 rounded"
                  style={{ color: 'var(--c-accent)', border: '1px solid var(--c-accent-border)' }}
                >
                  Recommended layout
                </button>
                <button onClick={addAgent}
                  className="text-[10px] font-mono px-2 py-0.5 rounded"
                  style={{ color: 'var(--c-accent)', border: '1px solid var(--c-accent-border)' }}>
                  + Add
                </button>
              </div>
            }>
              {/* Recommended layout confirmation */}
              {showRecConfirm && (
                <div className="mb-2 p-3 rounded border text-[10px] font-mono space-y-2"
                  style={{ borderColor: 'var(--c-accent-border)', background: 'var(--c-accent-dim)' }}
                >
                  <p style={{ color: 'var(--c-text-2)' }}>
                    Apply the recommended 9-agent layout? This will <strong style={{ color: '#f59e0b' }}>replace</strong> all current agents.
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={applyRecommendedLayout}
                      className="px-3 py-1 rounded font-bold"
                      style={{ background: 'var(--c-accent)', color: '#000' }}
                    >
                      Apply and replace
                    </button>
                    <button
                      onClick={() => setShowRecConfirm(false)}
                      className="px-3 py-1 rounded"
                      style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {recMsg && (
                <p className="mb-2 text-[10px] font-mono" style={{ color: '#f59e0b' }}>{recMsg}</p>
              )}
              {cfg.agents.map((agent, idx) => (
                <AgentEditor
                  key={idx}
                  agent={agent}
                  isManager={agent.id === 'manager'}
                  onUpdate={(key, val) => updateAgent(idx, key, val)}
                  onApplyPreset={(fields) => applyAgentPreset(idx, fields)}
                  onRemove={() => removeAgent(idx)}
                />
              ))}
              {cfg.agents.length === 0 && (
                <p className="text-[11px] font-mono text-center py-4" style={{ color: 'var(--c-text-4)' }}>
                  No agents — click + Add
                </p>
              )}
            </Section>
              </>
            ) : (
              <motion.div key="account" className="pt-4">
                <p className="text-[10px] mb-4" style={{ color: 'var(--c-text-3)' }}>
                  Account and theme settings are available at the settings page.
                </p>
                <button
                  onClick={() => { navigate('/settings'); onClose() }}
                  className="w-full text-xs py-2 rounded font-bold transition-colors"
                  style={{ background: 'var(--c-accent)', color: '#000' }}
                >
                  Open Settings →
                </button>
              </motion.div>
            )}
            </AnimatePresence>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 px-5 py-3 shrink-0" style={{ borderTop: '1px solid var(--c-border)' }}>
            <button onClick={onClose}
              className="text-xs font-mono px-4 py-1.5 rounded"
              style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-2)' }}>
              Close
            </button>
            {activeTab === 'project' && (
              <button
                onClick={handleSave}
                disabled={saving || saved}
                className="text-xs font-mono px-4 py-1.5 rounded transition-all"
                style={
                  saved
                    ? { border: '1px solid #22c55e', color: '#22c55e', background: 'rgba(34,197,94,0.1)' }
                    : saving
                    ? { border: '1px solid var(--c-border)', color: 'var(--c-text-4)', cursor: 'wait' }
                    : { border: '1px solid var(--c-accent-border)', color: 'var(--c-accent)' }
                }
              >
                {saved ? '✓ Saved' : saving ? 'Saving…' : 'Save & Apply'}
              </button>
            )}
          </div>
        </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

// ── sub-components ────────────────────────────────────────────────────────────

function Section({ title, children, action }: {
  title: string; children: React.ReactNode; action?: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>{title}</span>
        {action}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--c-text-3)' }}>{label}</span>
      {children}
    </div>
  )
}

const inputCls = 'flex-1 text-[11px] font-mono rounded px-2 py-1 focus:outline-none'

function inputStyle(): React.CSSProperties {
  return {
    background: 'var(--c-input-bg)',
    border: '1px solid var(--c-border)',
    color: 'var(--c-text-1)',
  }
}

interface AgentEditorProps {
  agent: AgentCfg
  isManager: boolean
  onUpdate: (key: keyof AgentCfg, val: string | number | boolean) => void
  onApplyPreset: (fields: Partial<AgentCfg>) => void
  onRemove: () => void
}

function AgentEditor({ agent, isManager, onUpdate, onApplyPreset, onRemove }: AgentEditorProps) {
  const [expanded, setExpanded] = useState(false)

  const matchedPreset = AGENT_PRESETS.find(p => p.id === agent.id)
  const presetValue = matchedPreset ? matchedPreset.id : '__custom__'

  const handlePresetChange = (id: string) => {
    if (id === '__custom__') {
      onUpdate('id', '')
      return
    }
    const preset = AGENT_PRESETS.find(p => p.id === id)
    if (!preset) return
    onApplyPreset({
      id: preset.id,
      name: preset.name,
      role: preset.role,
      icon: preset.icon,
      color: preset.color,
      planner: preset.planner,
      system_prompt: preset.prompt,
    })
  }

  return (
    <div className="rounded overflow-hidden" style={{ border: '1px solid var(--c-border)', background: 'var(--c-surface-3)' }}>
      {/* Collapsed row */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        {/* Icon picker */}
        <div className="relative shrink-0">
          <select
            value={agent.icon}
            onChange={e => { e.stopPropagation(); onUpdate('icon', e.target.value) }}
            onClick={e => e.stopPropagation()}
            className="absolute inset-0 opacity-0 cursor-pointer w-full"
          >
            {ICONS.map(ic => <option key={ic} value={ic}>{ic}</option>)}
          </select>
          <span className="text-base select-none">{agent.icon}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <input
              className="text-[11px] font-mono bg-transparent font-semibold w-24 focus:outline-none border-b border-transparent focus:border-white/20"
              style={{ color: 'var(--c-text-1)' }}
              value={agent.name}
              onChange={e => onUpdate('name', e.target.value)}
              onClick={e => e.stopPropagation()}
              placeholder="Name"
            />
            <span className="text-[10px]" style={{ color: 'var(--c-text-4)' }}>/</span>
            <input
              className="text-[10px] font-mono bg-transparent flex-1 min-w-0 focus:outline-none border-b border-transparent focus:border-white/20"
              style={{ color: 'var(--c-text-3)' }}
              value={agent.role}
              onChange={e => onUpdate('role', e.target.value)}
              onClick={e => e.stopPropagation()}
              placeholder="Role"
            />
          </div>
          <div className="text-[9px] font-mono mt-0.5 truncate" style={{ color: 'var(--c-text-4)' }}>
            {KNOWN_MODELS.find(m => m.id === agent.model)?.label ?? agent.model}
            {(agent.model.startsWith('gpt-') || agent.model.startsWith('claude-') || agent.model.startsWith('gemini-')) && (
              <> <span style={{ color: 'var(--c-text-4)' }}>(expensive)</span></>
            )}
          </div>
        </div>

        {/* Color swatch */}
        <div className="relative shrink-0" onClick={e => e.stopPropagation()}>
          <input
            type="color"
            value={agent.color}
            onChange={e => onUpdate('color', e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
          />
          <div className="w-4 h-4 rounded-full" style={{ background: agent.color, border: '1px solid var(--c-border)' }} />
        </div>

        <span className="text-[10px] select-none ml-1" style={{ color: 'var(--c-text-3)' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 pt-1 space-y-2" style={{ borderTop: '1px solid var(--c-border)' }}>

              {/* Role preset selector */}
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--c-text-3)' }}>Role</span>
                <div className="flex-1">
                  <select
                    value={presetValue}
                    onChange={e => { e.stopPropagation(); handlePresetChange(e.target.value) }}
                    onClick={e => e.stopPropagation()}
                    disabled={isManager}
                    className={`w-full text-[11px] font-mono rounded px-2 py-1 focus:outline-none appearance-none cursor-pointer ${isManager ? 'opacity-40' : ''}`}
                    style={inputStyle()}
                  >
                    <option value="__custom__">Custom</option>
                    <option value="manager">{MANAGER_PRESET.icon} {MANAGER_PRESET.name} — {MANAGER_PRESET.role}</option>
                    <optgroup label="── Planners ──">
                      {PLANNER_PRESETS.map(p => (
                        <option key={p.id} value={p.id}>{p.icon} {p.name} — {p.role}</option>
                      ))}
                    </optgroup>
                    <optgroup label="── Executors ──">
                      {EXECUTOR_PRESETS.map(p => (
                        <option key={p.id} value={p.id}>{p.icon} {p.name} — {p.role}</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
              </div>

              {/* Custom ID input (when no preset matches) */}
              {presetValue === '__custom__' && (
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--c-text-3)' }}>ID</span>
                  <input
                    className={inputCls}
                    style={inputStyle()}
                    value={agent.id}
                    onChange={e => onUpdate('id', e.target.value)}
                    onClick={e => e.stopPropagation()}
                    placeholder="agent-id"
                  />
                </div>
              )}

              {/* System prompt */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>
                    System Prompt
                  </span>
                  {isManager && (
                    <span className="text-[9px] font-mono" style={{ color: 'var(--c-text-4)' }}>
                      auto-generated from team
                    </span>
                  )}
                </div>
                <textarea
                  rows={8}
                  className="w-full text-[10px] font-mono rounded px-2 py-1.5 focus:outline-none resize-y leading-relaxed"
                  style={{ ...inputStyle(), opacity: isManager ? 0.45 : 1, minHeight: '120px' }}
                  value={isManager ? '(Auto-generated based on team composition — defines the JSON output format for task delegation)' : (agent.system_prompt ?? '')}
                  onChange={e => { if (!isManager) onUpdate('system_prompt', e.target.value) }}
                  onClick={e => e.stopPropagation()}
                  readOnly={isManager}
                  placeholder="Describe this agent's role, responsibilities, boundaries, and how it should interact with other agents…"
                />
              </div>

              {/* Model */}
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--c-text-3)' }}>Model</span>
                <div className="flex-1 relative">
                  <select
                    value={KNOWN_MODELS.some(m => m.id === agent.model) ? agent.model : '__custom__'}
                    onChange={e => { if (e.target.value !== '__custom__') onUpdate('model', e.target.value) }}
                    onClick={e => e.stopPropagation()}
                    className="w-full text-[11px] font-mono rounded px-2 py-1 focus:outline-none appearance-none cursor-pointer"
                    style={inputStyle()}
                  >
                    {MODEL_GROUPS.map(group => (
                      <optgroup key={group.label} label={`── ${group.label} ──`}>
                        {group.models.map(m => (
                          <option key={m.id} value={m.id}>
                            {m.label}{m.id.startsWith('gpt-') || m.id.startsWith('claude-') || m.id.startsWith('gemini-') ? ' (expensive)' : ''}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                    {!KNOWN_MODELS.some(m => m.id === agent.model) && (
                      <option value="__custom__">Custom…</option>
                    )}
                  </select>
                </div>
              </div>

              {/* Custom model input */}
              {!KNOWN_MODELS.some(m => m.id === agent.model) && (
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--c-text-3)' }}>Custom</span>
                  <input
                    className={inputCls}
                    style={inputStyle()}
                    value={agent.model}
                    onChange={e => onUpdate('model', e.target.value)}
                    onClick={e => e.stopPropagation()}
                    placeholder="provider/model-id"
                  />
                </div>
              )}

              {/* Sampling */}
              <div className="pt-1 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>Sampling</span>
                  {MODEL_RECOMMENDATIONS[agent.model] && (
                    <button
                      onClick={() => {
                        const r = MODEL_RECOMMENDATIONS[agent.model]
                        onUpdate('temperature', r.temperature)
                        onUpdate('top_p', r.top_p)
                        onUpdate('top_k', r.top_k ?? 0)
                        onUpdate('thinking_budget', r.thinking_budget ?? 0)
                      }}
                      className="text-[9px] font-mono px-2 py-0.5 rounded flex items-center gap-1"
                      style={{ color: 'var(--c-accent)', border: '1px solid var(--c-accent-border)', background: 'var(--c-accent-dim)' }}
                      title={MODEL_RECOMMENDATIONS[agent.model].note}
                    >
                      ✦ Recommended
                      {MODEL_RECOMMENDATIONS[agent.model].note && (
                        <span style={{ color: 'var(--c-text-4)' }}>· {MODEL_RECOMMENDATIONS[agent.model].note}</span>
                      )}
                    </button>
                  )}
                </div>
                <Slider label="Temp" value={agent.temperature} min={0} max={2} step={0.05}
                  onChange={v => onUpdate('temperature', v)} />
                <Slider label="Top-P" value={agent.top_p} min={0} max={1} step={0.05}
                  onChange={v => onUpdate('top_p', v)} />
                <Slider label="Top-K" value={agent.top_k ?? 0} min={0} max={100} step={1}
                  onChange={v => onUpdate('top_k', v)} />
                {(agent.top_k ?? 0) === 0 && (
                  <p className="text-[9px] font-mono pl-0.5" style={{ color: 'var(--c-text-4)' }}>Top-K = 0 means disabled</p>
                )}
                <Slider
                  label="Think"
                  value={agent.thinking_budget ?? 0}
                  min={0} max={16000} step={256}
                  disabled={!THINKING_CAPABLE_MODELS.has(agent.model)}
                  onChange={v => onUpdate('thinking_budget', v)}
                />
                {(agent.thinking_budget ?? 0) === 0 && THINKING_CAPABLE_MODELS.has(agent.model) && (
                  <p className="text-[9px] font-mono pl-0.5" style={{ color: 'var(--c-text-4)' }}>0 = no reasoning</p>
                )}
                {!THINKING_CAPABLE_MODELS.has(agent.model) && (
                  <p className="text-[9px] font-mono pl-0.5" style={{ color: 'var(--c-text-4)' }}>This model does not support thinking</p>
                )}
              </div>

              {/* Remove */}
              <div className="flex justify-end pt-1">
                <button
                  onClick={onRemove}
                  className="text-[10px] font-mono px-2 py-0.5 rounded"
                  style={{ color: 'rgba(248,113,113,0.7)', border: '1px solid rgba(239,68,68,0.25)' }}
                >
                  Remove agent
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}


# Support Orchestrator Demo

A multi-agent customer support workflow built on the Thenvoi platform. When a customer reports a bug, the orchestrator kicks off 3 parallel investigations (customer data lookup, GitHub issue search, browser reproduction), then synthesizes the results into an informed response.

## Architecture

```
            R-user-support (User <-> SupportOrchestrator)
                          |
                 SupportOrchestrator (hub)
                /       |        \         \
          R-excel   R-github   R-browser   R-linear
             |         |          |            |
        ExcelAgent  GitHubAgent BrowserAgent LinearAgent
```

**5 Thenvoi rooms**, **5 agents** (1 orchestrator + 4 specialists).

LinearAgent is only invoked conditionally — when no GitHub match is found (Branch B).

## Workflow

See [`docs/workflow-a-broken-feature.md`](docs/workflow-a-broken-feature.md) for the full scenario.

**TL;DR:** Customer says "The export button is broken, sarah@acme.com" and the orchestrator:

1. **Acknowledges** immediately (<1s)
2. **Delegates in parallel** to:
   - **ExcelAgent** — looks up customer record (plan, features, account status)
   - **GitHubSupportAgent** — searches for matching open issues
   - **BrowserAgent** — reproduces the issue in a browser
3. **Synthesizes** results:
   - **Branch A** (known bug): GitHub match found — respond with issue #, timeline, workaround
   - **Branch B** (new bug): No match — delegate to LinearAgent — respond with ticket ID
   - **Branch C** (plan limitation): Feature not in plan — suggest upgrade

## Demo Product Repo

The GitHubSupportAgent searches a real GitHub repo populated with realistic issues:

**[roi-shikler-thenvoi/demo-product](https://github.com/roi-shikler-thenvoi/demo-product)** — "Acme Analytics" dashboard platform

Key issue for the demo: **[#8 — CSV export spinner hangs on dashboards with >500 rows](https://github.com/roi-shikler-thenvoi/demo-product/issues/8)** (bug, priority: high, customer-reported, confirmed), with an engineer comment linking to fix PR #21 and a "deploying Thursday" timeline.

The repo has 20 issues, 17 labels, and an open PR — giving the agent plenty of realistic context to triage from.

---

## Prerequisites

| Requirement | What it's for | Check |
|---|---|---|
| Python 3.11+ | All agents | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | Package management | `uv --version` |
| [Thenvoi SDK](https://github.com/thenvoi/thenvoi-sdk-python) | Agent framework | `pip install thenvoi-sdk[langgraph]` |
| [LangGraph](https://github.com/langchain-ai/langgraph) + LLM provider | LLM agent framework | Installed via `pip install -e ".[dev]"` |
| Anthropic API key **or** OpenAI API key | LLM for all agents | Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env` |
| Thenvoi User API key (`thnv_u_...`) | Register agents + create rooms | Get from [app.thenvoi.com](https://app.thenvoi.com) settings |
| [gh CLI](https://cli.github.com/) + GitHub token | GitHubSupportAgent searches issues | `gh auth status` |

---

## Setup (one-time)

### Step 1: Create a virtualenv and install dependencies

```bash
git clone https://github.com/thenvoi/support-orchestrator-demo.git
cd support-orchestrator-demo
uv venv
source .venv/bin/activate

# Install this project and all dependencies (includes Thenvoi SDK, pandas, etc.)
uv pip install -e ".[dev]"
```

### Step 2: Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in the two required values:

```
THENVOI_API_KEY=thnv_u_your_user_api_key_here
GITHUB_TOKEN=ghp_your_github_token_here
```

The `THENVOI_REST_URL` and `THENVOI_WS_URL` defaults are fine for production Thenvoi.

### Step 3: Generate the mock customer database

```bash
python demo_data/generate_customers.py
```

Verify: `demo_data/customers.xlsx` should exist with 18 rows. Key records:
- `sarah@acme.com` — Pro plan, CSV Export included (triggers Branch A/B)
- `john@startup.io` — Free plan, no CSV Export (triggers Branch C)

### Step 4: Register agents and create rooms on Thenvoi

```bash
cd src
python -m thenvoi_integration.setup_demo
```

This does everything:
1. Registers 5 agents (SupportOrchestrator, ExcelAgent, GitHubSupportAgent, BrowserAgent, LinearAgent)
2. Creates 5 rooms with the hub-and-spoke topology
3. Adds the correct agents as participants in each room
4. Saves agent IDs + one-time API keys to `src/config/agent_config.yaml`
5. Saves orchestrator credentials + room IDs to `.env`

After setup, `.env` will have these auto-populated:
```
THENVOI_AGENT_ID=<orchestrator-agent-id>
THENVOI_USER_API_KEY=<your-user-key-preserved>
SUPPORT_USER_ROOM_ID=<room-id>
SUPPORT_EXCEL_ROOM_ID=<room-id>
SUPPORT_GITHUB_ROOM_ID=<room-id>
SUPPORT_BROWSER_ROOM_ID=<room-id>
SUPPORT_LINEAR_ROOM_ID=<room-id>
```

And `src/config/agent_config.yaml` will contain all 5 agents' credentials:
```yaml
agents:
  support_orchestrator:
    agent_id: <uuid>
    api_key: thnv_a_...
  excel:
    agent_id: <uuid>
    api_key: thnv_a_...
  github_support:
    agent_id: <uuid>
    api_key: thnv_a_...
  browser:
    agent_id: <uuid>
    api_key: thnv_a_...
  linear:
    agent_id: <uuid>
    api_key: thnv_a_...
```

---

## Running the Demo

You need **6 terminals**: 1 for the mock web server + 5 for the agents. All commands run from the `support-orchestrator-demo/` directory.

### Terminal 1 — Mock web app (for BrowserAgent)

```bash
cd demo_data && python -m http.server 8888
```

Verify: open http://localhost:8888/mock_app.html — you should see an "Acme Analytics" dashboard with an "Export to CSV" button that hangs when clicked.

### Terminal 2 — SupportOrchestrator

The orchestrator reads its credentials from `.env` (auto-populated by setup).

```bash
cd src
python -m orchestrator.orchestrator
```

### Terminals 3–6 — Specialist agents

Each specialist needs its **own** `THENVOI_AGENT_ID` and `THENVOI_API_KEY` from `agent_config.yaml`. Open the file, find each agent's credentials, and paste them in:

**Terminal 3 — ExcelAgent:**
```bash
cd src
THENVOI_AGENT_ID=<paste excel agent_id> \
THENVOI_API_KEY=<paste excel api_key> \
python -m agents.excel.agent
```

**Terminal 4 — GitHubSupportAgent:**
```bash
cd src
THENVOI_AGENT_ID=<paste github_support agent_id> \
THENVOI_API_KEY=<paste github_support api_key> \
python -m agents.github.agent
```

**Terminal 5 — BrowserAgent:**
```bash
cd src
THENVOI_AGENT_ID=<paste browser agent_id> \
THENVOI_API_KEY=<paste browser api_key> \
python -m agents.browser.agent
```

**Terminal 6 — LinearAgent:**
```bash
cd src
THENVOI_AGENT_ID=<paste linear agent_id> \
THENVOI_API_KEY=<paste linear api_key> \
python -m agents.linear.agent
```

### Send the test message

Once all agents are running, go to the [Thenvoi UI](https://app.thenvoi.com) and open the **R-user-support** room. Send:

> The export-to-CSV button on my dashboard just spins and nothing downloads. My account is sarah@acme.com.

**What should happen:**

1. SupportOrchestrator acknowledges immediately
2. Three parallel investigations kick off:
   - ExcelAgent finds Sarah Chen — Pro plan, CSV Export included, account active
   - GitHubSupportAgent finds [issue #8](https://github.com/roi-shikler-thenvoi/demo-product/issues/8) — "CSV export spinner hangs on dashboards with >500 rows", with engineer comment about PR #21 deploying Thursday
   - BrowserAgent navigates to the mock app, clicks Export, sees the spinner hang, reads `TimeoutError` from console
3. SupportOrchestrator synthesizes: **Branch A** — known bug, issue #8, fix deploying Thursday, workaround is to filter below 500 rows

---

## Test Scenarios

| Scenario | Message to send | Expected Branch | What happens |
|----------|----------------|-----------------|-------------|
| **Known bug** | "Export button broken, sarah@acme.com" | Branch A | GitHub finds #8, responds with timeline + workaround |
| **New bug** | "The chart tooltips are completely invisible, sarah@acme.com" | Branch B | No exact GitHub match → LinearAgent files a ticket |
| **Plan limitation** | "Export button broken, john@startup.io" | Branch C | Excel shows Free plan, no CSV Export → suggests upgrade |

---

## Teardown

To delete all agents and clean up:

```bash
cd src
python -m thenvoi_integration.teardown_demo
```

This force-deletes all 5 agents. Chat rooms are cleaned up automatically when agents are removed.

After teardown, you may want to manually remove the auto-generated variables from `.env` (everything below the `# --- Below are auto-populated` comment).

---

## Project Structure

```
support-orchestrator-demo/
├── src/
│   ├── agents/
│   │   ├── base_specialist.py       # Base class for all specialists (LangGraph)
│   │   ├── excel/agent.py           # Customer data lookup (pandas @tool)
│   │   ├── github/agent.py          # Bug triage (gh CLI @tool)
│   │   ├── browser/agent.py         # Issue reproduction (mock @tool)
│   │   └── linear/agent.py          # Bug filing (mock @tool)
│   ├── orchestrator/
│   │   └── orchestrator.py          # SupportOrchestrator + OrchestratorAdapter (LangGraph)
│   ├── thenvoi_integration/
│   │   ├── agent_registry.py        # Agent CRUD via Thenvoi API
│   │   ├── room_manager.py          # Room CRUD via Thenvoi API
│   │   ├── setup_demo.py            # Provision agents + rooms
│   │   └── teardown_demo.py         # Cleanup
│   └── config/
│       ├── agent_config.yaml.example # Template showing expected structure
│       └── agent_config.yaml        # Generated agent credentials (gitignored)
├── demo_data/
│   ├── customers.xlsx               # Mock customer database (18 rows)
│   ├── mock_app.html                # Broken export button page
│   └── generate_customers.py        # Script to regenerate xlsx
├── docs/
│   └── workflow-a-broken-feature.md  # Full workflow specification
├── pyproject.toml                   # Python project config
├── .env.example                     # Environment variable template
└── README.md                        # This file
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `setup_demo.py` fails with "THENVOI_API_KEY is not set" | Make sure `.env` has your user key (`thnv_u_...` prefix) |
| `gh` commands fail in GitHubSupportAgent | Verify `gh auth status` shows logged in and `GITHUB_TOKEN` is set in `.env` |
| BrowserAgent can't load MCP tools | Ensure `claude-in-chrome` MCP server is configured in your Claude Code settings and Chrome extension is running |
| LinearAgent can't load MCP tools | Ensure `plugin_linear_linear` MCP server is configured in your Claude Code settings |
| Mock app doesn't load at localhost:8888 | Make sure `python -m http.server 8888` is running from `demo_data/` |
| Specialist agent says "THENVOI_AGENT_ID must be set" | Each specialist needs its own credentials — copy from `agent_config.yaml`, not from `.env` |

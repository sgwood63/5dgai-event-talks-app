# ambient-expense-agent

Ambient expense-approval agent built with ADK 2.0.

## Project Structure

```
ambient-expense-agent/
├── expense_agent/     # Core agent code
│   ├── agent.py               # Main agent logic & graph definition
│   ├── config.py              # Configuration & thresholds
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and server e2e tests
├── GEMINI.md                  # AI-assisted development guide
├── Makefile                   # Installation & execution shortcuts
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager - [Install](https://docs.astral.sh/uv/getting-started/installation/)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For optional GCP telemetry - [Install](https://cloud.google.com/sdk/docs/install)

## Quick Start

1. **Install required packages**:
   ```bash
   make install
   ```

2. **Launch the local web server / developer playground**:
   ```bash
   make playground
   ```
   The playground will be running at [http://127.0.0.1:8080/dev-ui/?app=expense_agent](http://127.0.0.1:8080/dev-ui/?app=expense_agent).

---

## 🤖 Using Gemini in the Playground & Tests

The agent utilizes the `gemini-3.1-flash-lite` model for reviewing high-value transactions (amount >= $100). 

### 1. Developer Playground
* **Default Mode (API Key-less Mocking)**: If no Gemini API key or GCP credentials are present, the agent automatically swaps in a `MockGemini` class. This allows you to launch the playground and run verify payloads without startup crashes, outputting mock compliance reviews.
* **Live Gemini Mode**: To run the playground against the live Gemini API, export your API key before starting the playground:
  ```bash
  export GEMINI_API_KEY="your-api-key-here"
  make playground
  ```

### 2. Running Tests
* **Mocked Integration Tests**: By default, running tests uses mock responses for the LLM node:
  ```bash
  pytest
  ```
* **Live Integration Tests**: To run the integration tests against the live Gemini model, set `REAL_GEMINI=1` and provide your API key:
  ```bash
  REAL_GEMINI=1 GEMINI_API_KEY="your-api-key-here" pytest
  ```

---

## Commands

| Command | Description |
|---------|-------------|
| `make install` / `agents-cli install` | Install all dependencies |
| `make playground` / `agents-cli playground` | Launch local development playground |
| `agents-cli lint` | Run code quality checks |
| `agents-cli eval` | Evaluate agent behavior |
| `pytest` | Run the full test suite (integration & E2E) |

## 🛠️ Project Management

| Command | What It Does |
|---------|--------------|
| `agents-cli scaffold enhance` | Add CI/CD pipelines and Terraform infrastructure |
| `agents-cli scaffold upgrade` | Auto-upgrade to latest version while preserving customizations |

## Development

Edit your agent logic in `expense_agent/agent.py` and test with `agents-cli playground` - it auto-reloads on save.

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

## Observability

Built-in telemetry exports to Cloud Trace and Cloud Logging when running on GCP with valid credentials. Local execution automatically falls back to standard file logging.

# AI Digest & Ideas 🚀

Professional pipeline for discovering, ranking, and summarizing trends for technical audiences and solo founders. Designed to track AI, Dev, Design, and Marketing topics while uncovering actionable business ideas with high precision and low noise.

## ✨ Key Features

- **Multi-Source Discovery**: Scans X (Twitter), Reddit, Hacker News, Product Hunt, Indie Hackers, Habr, and VC.ru.
- **AI-Powered Filtering**: Uses `google/gemini-3-flash-preview` to select the most actionable content specifically for solo developers and small teams.
- **Business Idea Radar**: A specialized sub-pipeline that scans comments on Reddit/HN and posts on X to identify real user pain points. It transforms these "whining" signals into structured business ideas including:
  - **The Pain**: Detailed problem description.
  - **The Solution**: Proposed MVP strategy.
  - **ICP**: Target audience and buying potential.
  - **Scoring**: 0-100 rating based on evidence density and market potential.
- **Smart Formatting**: Sends clean, readable Telegram digests with "Clean Titles" and "Why it matters" explanations for every post.
- **Total Cost Tracking**: Transparent reporting of LLM token usage and costs for every daily run.

## 🛠 Tech Stack

- **Core**: Python 3.9+
- **LLM**: Gemini 3 Flash (via OpenRouter)
- **Database/Memory**: Local JSON-based memory store for deduplication
- **Notifications**: Telegram Bot API

## 🚀 Getting Started

### 1. Installation

```bash
git clone https://github.com/geoinvestbtc-x/ai-digest-and-ideas.git
cd ai-digest-and-ideas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file in the root directory:

```env
# --- GENERAL SECRETS ---
OPENROUTER_API_KEY=your_key_here

# --- TELEGRAM SETTINGS ---
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=@your_channel_or_chat_id

# --- X / TWITTER API ---
TWITTERAPI_IO_KEY=your_twitterapi_io_key

# --- MODELS & CONFIG ---
LLM_MODEL=google/gemini-3-flash-preview
DIGEST_MAX_PER_TOPIC=10
```

### 3. Usage

To run the complete daily pipeline (Category Digests + Business Idea Radar):

```bash
source .venv/bin/activate
python3 scripts/digest/run_daily.py
```

**Available Flags:**
- `--dry-run`: Run the entire pipeline without sending results to Telegram (prints to console).
- `--only-digest`: Run only the category-based trend digests.
- `--only-radar`: Run only the Business Idea Radar.

## 📡 Category Coverage

The system currently tracks and filters content for:
- 📣 **AI Marketing** — growth tactics and automation
- ⚡ **AI Coding** — agentic workflows and developer tools
- 🧠 **General AI** — model updates and infrastructure
- 🎨 **AI Design** — UI/UX automation and component generation
- 🦞 **OpenClaw** — automation frameworks and agent patterns
- 🐙 **GitHub Projects** — boilerplates and time-saving libraries

## 🤖 CI/CD

A GitHub Actions workflow is included in `.github/workflows/pipeline.yml` for manual dry-run verification of the pipeline.

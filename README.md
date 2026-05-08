# 🤖 Multimodal AI Chatbot

A production-ready, multi-channel AI chatbot built with **FastAPI**, **LangGraph**, **Groq (Llama 3)**, **Google Gemini**, **ChromaDB** (RAG), **SQLite**, and **Whisper** (local STT).

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│                                                            │
│  ┌──────────────┐                    ┌──────────────────┐ │
│  │  /webhook/   │                    │      /chat       │ │
│  │  telegram    │                    │  (REST + WS)     │ │
│  └──────┬───────┘                    └────────┬─────────┘ │
│         │                                     │           │
│         └─────────────────────────────────────┘           │
│                           │                               │
│                  MessageNormalizer                        │
│                  (unified format)                         │
│                           │                               │
│                  ┌────────▼────────┐                      │
│                  │  AudioHandler   │  (Whisper STT)       │
│                  └────────┬────────┘                      │
│                           │                               │
│              ┌────────────▼────────────┐                  │
│              │     LangGraph Workflow   │                  │
│              │  load_history           │                  │
│              │       ↓                 │                  │
│              │  rag_lookup (ChromaDB)  │                  │
│              │       ↓                 │                  │
│              │  generate_response      │                  │
│              │    (Groq / Gemini)      │                  │
│              │       ↓                 │                  │
│              │  save_history (SQLite)  │                  │
│              └─────────────────────────┘                  │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
chatbot-project/
├── main.py                        # FastAPI app, lifespan, routers
├── Dockerfile                     # Multi-stage Python build
├── docker-compose.yml             # App + ChromaDB + shared volumes
├── requirements.txt
├── .env.example                   # ← Copy to .env and fill in secrets
├── .gitignore
│
├── app/
│   ├── config.py                  # Pydantic-settings (all env vars)
│   ├── models.py                  # Shared Pydantic models
│   │
│   ├── routers/
│   │   ├── telegram.py            # POST /webhook/telegram
│   │   └── webchat.py             # POST /chat  +  WS /ws/{session_id}
│   │
│   ├── services/
│   │   ├── message_normalizer.py  # Converts raw payloads → NormalizedMessage
│   │   ├── audio_handler.py       # Download voice → Whisper → transcript
│   │   ├── llm_chain.py           # Groq + Gemini with fallback
│   │   ├── rag_service.py         # ChromaDB similarity search
│   │   └── monitoring.py          # LangSmith + Langfuse hooks
│   │
│   ├── graph/
│   │   └── workflow.py            # LangGraph stateful workflow
│   │
│   └── storage/
│       ├── database.py            # Async SQLite (chat_history, leads)
│       └── vector_store.py        # ChromaDB collection helpers
│
├── scripts/
│   ├── init_db.py                 # Create SQLite tables
│   └── init_chroma.py             # Seed FAQ documents into ChromaDB
│
├── static/
│   └── index.html                 # Standalone web chat widget (REST + WS)
│
└── .vscode/
    └── settings.json
```

---

## 🚀 Quick Start

### 0. Prerequisites

- Python 3.12
- Docker + Docker Compose

### 1. Clone and configure

```bash
git clone <your-repo>
cd chatbot-project
cp .env.example .env
# ✏️  Open .env and fill in your API keys
```

### 1.1 Create a venv (optional local install)

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### 2. Launch with Docker Compose

```bash
docker-compose up --build
```

That's it. The app will be available at **http://localhost:8000**

### 3. Seed the knowledge base (first run)

```bash
# While containers are running:
docker-compose exec app python scripts/init_chroma.py
```

Edit `scripts/init_chroma.py` to add your own FAQ content.

---

## 🔑 Required Environment Variables

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `GOOGLE_API_KEY` | https://aistudio.google.com/app/apikey |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram |

---

## 🌐 Webhook Setup

### Telegram

```bash
curl -X POST "https://api.telegram.org/bot{YOUR_TOKEN}/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://your-domain.com/webhook/telegram"}'
```

### Local development with ngrok

```bash
ngrok http 8000
# Use the https:// URL as your webhook base
```

---

## 🗣️ Voice Message Support

Voice notes from Telegram are automatically:
1. Downloaded from the platform's CDN
2. Transcribed locally using OpenAI Whisper (`base` model by default)
3. Treated as text messages in the LangGraph workflow

Change `WHISPER_MODEL_SIZE` in `.env` for different quality/speed tradeoffs:
- `tiny` → fastest, ~1GB RAM
- `base` → good balance (default)
- `small` / `medium` → higher accuracy
- `large-v3` → best quality, needs GPU

---

## 🔍 RAG / FAQ System

The bot checks ChromaDB for relevant FAQ entries **before** calling the LLM.
If a match with cosine similarity ≥ 0.65 is found, it's included as context.

To add your own knowledge base documents, edit `scripts/init_chroma.py` and re-run it.

---

## 📊 Monitoring

| Service | Enable |
|---|---|
| **LangSmith** | Set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` |
| **Langfuse** | Set `LANGFUSE_ENABLED=true` + keys |

---

## 🛠️ Development Tips

```bash
# Live logs
docker-compose logs -f app

# Run tests (add pytest later)
docker-compose exec app pytest

# Check ChromaDB health
curl http://localhost:8001/api/v1/heartbeat

# Check app health
curl http://localhost:8000/health

# Interactive API docs (dev mode only)
open http://localhost:8000/docs
```


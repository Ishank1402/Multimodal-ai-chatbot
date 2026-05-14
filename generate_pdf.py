import re
from fpdf import FPDF

# The content to write to the PDF
markdown_text = """
# Nova Chatbot - System Architecture & File Guide

This document explains the step-by-step architecture of the Nova Chatbot project. It covers what files are created, why they are needed, and how the entire system works together to process a user's message.

---

## 1. The Core Application Files

### main.py
* **What it is:** The central entry point of the application.
* **Why it's made:** To launch the FastAPI web server, initialize all the background services (like the database and AI models), and wire everything together.
* **Function:** It creates the FastAPI app, mounts the static web files (HTML/CSS), and connects the routers (`/chat`) so the internet can reach your backend.

### app/config.py
* **What it is:** The configuration hub.
* **Why it's made:** To securely manage environment variables (like API keys) without hardcoding them into the app.
* **Function:** It reads the `.env` file and creates a validated `Settings` object that the rest of the application uses to connect to Groq, Gemini, and the databases.

### app/models.py
* **What it is:** The shared data structures (Pydantic models).
* **Why it's made:** To ensure that all data flowing through the app is strictly typed and formatted correctly.
* **Function:** It defines `NormalizedMessage` (how a message looks internally), `ChatState` (the state of the LangGraph workflow), and database storage formats.

---

## 2. The API Endpoints (Routers)

### app/routers/webchat.py
* **What it is:** The web communication bridge.
* **Why it's made:** To handle incoming messages specifically from the web widget (`index.html`).
* **Function:** It provides two doors:
  1. **REST (`/chat`):** Used primarily to upload voice recordings.
  2. **WebSocket (`/ws/...`):** Used for real-time text chatting, allowing the AI to stream its response back instantly.

---

## 3. The Backend Services (The "Brains")

### app/services/message_normalizer.py
* **What it is:** The message translator.
* **Why it's made:** If you ever add platforms like WhatsApp or Discord, they all send data differently. 
* **Function:** It takes the raw JSON payload from the web chat and turns it into a clean, standard `NormalizedMessage` so the rest of the app doesn't have to worry about where the message came from.

### app/services/audio_handler.py
* **What it is:** The ears of the bot.
* **Why it's made:** To process user voice messages locally without paying for API calls.
* **Function:** It uses **OpenAI Whisper** (a local machine learning model) and **FFmpeg** to take uploaded voice notes and transcribe them into text so the language model can read them.

### app/services/rag_service.py
* **What it is:** The knowledge retriever.
* **Why it's made:** Large Language Models don't know your specific business rules, services, or FAQs.
* **Function:** It connects to **ChromaDB** (a vector database). When a user asks a question, this service searches ChromaDB for the closest matching FAQ and gives that context to the AI.

### app/services/llm_chain.py
* **What it is:** The AI connector.
* **Why it's made:** To talk to external AI providers (Groq and Google Gemini) and manage their system prompts.
* **Function:** It constructs the prompt (telling the bot "Your name is Nova..."), formats the chat history, adds the RAG context, and then asks the LLM to generate an answer. It also has an automatic fallback so if Groq goes down, it instantly switches to Gemini.

---

## 4. The Workflow & Storage

### app/graph/workflow.py
* **What it is:** The LangGraph state machine (The orchestrator).
* **Why it's made:** Simple LLM calls aren't enough for complex bots. You need a workflow: load history -> search FAQs -> generate answer -> save history.
* **Function:** It strings all the services together into a logical flowchart. Every message passes through these exact nodes in order.

### app/storage/database.py
* **What it is:** The memory bank.
* **Why it's made:** So the bot remembers what you talked about 5 minutes ago.
* **Function:** Connects to a local **SQLite** database to save every message sent by the user and the bot.

---

## 5. The Initialization Scripts

### scripts/init_chroma.py
* **Function:** This is a one-off script you run to teach the bot specific facts. It uploads your custom FAQ entries into ChromaDB.

### scripts/init_db.py
* **Function:** Creates the initial SQLite database tables if they don't exist yet.

---

## 6. The User Interface

### static/index.html
* **What it is:** The visual chat widget.
* **Why it's made:** So you actually have something to interact with in your browser!
* **Function:** Contains the HTML, CSS, and Javascript required to record audio, connect via WebSockets, and display messages with a beautiful dark-mode UI.

---

## 🏗️ How the Architecture Fits Together

1. **User Types a Message:** The user opens `index.html` and hits send.
2. **WebSocket Receives It:** `routers/webchat.py` receives the text over the live connection.
3. **Normalization:** `message_normalizer.py` converts the text into a strict data format.
4. **LangGraph Workflow Begins:** `workflow.py` takes over.
5. **Load History:** The workflow asks `database.py` for previous messages.
6. **RAG Lookup:** The workflow asks `rag_service.py` (ChromaDB) if there are any FAQs relevant to the user's message.
7. **Generate:** The workflow passes all this (History + FAQ + Message) to `llm_chain.py`, which asks Groq/Gemini to generate a reply.
8. **Save & Return:** The workflow saves the reply to SQLite, and `webchat.py` streams the final text back to the user's screen.
"""

class PDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 15)
        self.cell(0, 10, "Nova Chatbot Architecture Guide", align="C")
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

# Clean up Markdown for FPDF2 basic Markdown support
# FPDF2 Markdown supports **, *, but not complex lists seamlessly yet depending on version, 
# but it should handle basic bolding and headers.
pdf = PDF()
pdf.add_page()
pdf.set_font("helvetica", size=12)

# Write HTML or Markdown natively
try:
    # write_markdown is available in newer fpdf2 versions
    pdf.write_markdown(markdown_text)
except AttributeError:
    # Fallback to multi_cell if markdown isn't fully supported
    pdf.multi_cell(0, 6, text=markdown_text)

pdf.output("Nova_Architecture_Guide.pdf")
print("Successfully generated Nova_Architecture_Guide.pdf!")

# 🌌 AURA (Augmented Understanding And Response Agent)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-brightgreen)](https://fastapi.tiangolo.com/)
[![Model: Phi-3](https://img.shields.io/badge/Model-Phi--3_Mini-blueviolet)](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

**AURA** is a next-generation, AI-powered personal productivity assistant designed to seamlessly integrate chat, task management, scheduling, and knowledge retrieval into a single, cohesive interface. Built with a "dark-mode first" philosophy, it offers a premium, glassmorphism-inspired UI that feels alive and responsive.

---

## ✨ Key Features

### 💬 Intelligent Chat Interface
- **Context-Aware AI**: Powered by **Local LLM (Phi-3 Mini via LlamaCPP)** for privacy-first, offline-capable, and context-rich conversations.
- **Markdown & Code Support**: Beautiful rendering of code blocks, tables, and formatted text.
- **Real-time Streaming**: Instant responses with typing indicators and smooth animations.
- **Memory & Context**: Remembers previous interactions for a continuous dialogue flow.

### 📋 Kanban Task Management
- **Visual Board**: Drag-and-drop Kanban board (To Do, In Progress, Done).
- **Smart Categorization**: Auto-tagging and prioritization of tasks.
- **Detailed Cards**: Rich task details including due dates, priority badges, and descriptions.
- **Seamless Integration**: Create tasks directly from chat conversations.

### 📅 Dynamic Calendar & Scheduling
- **Daily Timeline View**: Precision daily planner with a vertical timeline layout.
- **Magic Schedule**: AI-powered auto-scheduling that optimizes your day based on tasks and priorities.
- **Event Management**: Visual distinction between tasks, meetings, breaks, and deep work blocks.
- **Time Blocking**: Drag-and-drop time allocation for focused productivity.

### 🧠 Knowledge Base (RAG)
- **Document Ingestion**: Upload and index documents (PDF, TXT, MD) for AI retrieval.
- **Semantic Search**: Ask questions about your uploaded documents.
- **Contextual Answers**: The AI cites sources and uses your knowledge base to answer queries.

### 📊 Insights & Analytics
- **Focus Score**: Real-time productivity tracking and focus metrics.
- **Activity Trends**: Visual charts showing task completion and productivity over time.
- **Productivity Distribution**: Analysis of time spent on different categories (Work, Learning, Health).

---

## 🛠 Technology Stack

| Component | Technologies |
|-----------|--------------|
| **Backend API** | FastAPI, Uvicorn, SQLAlchemy, Pydantic |
| **AI Engine** | Local LLM (Phi-3 Mini), LlamaCPP, SentenceTransformers |
| **Database** | SQLite (Local), ChromaDB (Vector Store) |
| **Frontend** | HTML5, Vanilla CSS (Glassmorphism), JavaScript (ES6+) |
| **Visualization** | Chart.js, Lucide Icons |
| **Deployment** | Docker (Optional), Python-dotenv |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- 4GB+ RAM (8GB+ recommended for best performance)
- Modern Web Browser

Copy .env.example to .env for local configuration. The real .env is ignored by Git; never commit credentials or machine-specific settings.

The core API can be imported and started without a GGUF model, GPU, ChromaDB data, embedding downloads, OCR binaries, or user documents. Local AI/RAG and document features require the optional dependencies and model/system prerequisites documented in `docs/runtime.md`. Protected API operations require registration/login; see `docs/authentication.md`.

See docs/runtime.md for the core, AI, and RAG install profiles, explicit model/embedding provisioning, verification, CPU/GPU behavior, and health/readiness diagnostics.

### Installation

1. **Clone the Repository**
```bash
git clone https://github.com/your-username/aura-assistant.git
cd aura-assistant
```

2. **Set Up Environment**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
```

3. **Download Models**
Run the model downloader to fetch the GGUF model and embeddings:
```bash
python backend/download_models.py
```

4. **Configure Environment Variables**
Create a `.env` file in the root directory by copying `.env.example`; never commit that local file. Set a unique `AUTH_SECRET_KEY` before exposing the API and configure explicit `ALLOWED_ORIGINS`.
```env
# Optional: Customize model usage
USE_GPU=true
MODEL_FILENAME=Phi-3-mini-4k-instruct-q4.gguf
DATABASE_URL=sqlite:///./aura.db
```

5. **Start the Backend Server**
```bash
python backend/run_backend.py
# Server will start at http://localhost:8000
```

5. **Launch the Application**
Open `frontend/index.html` in your browser or serve it using a simple HTTP server:
```bash
cd frontend
python -m http.server 3000
# Access at http://localhost:3000
```

---

## 📁 Project Structure

```
AURA/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── models/                 # Database models
│   │   ├── routes/                 # API endpoints (chat, tasks, schedule)
│   │   ├── services/               # Business logic (AI, RAG, Calendar)
│   │   └── utils/                  # Helper functions
│   └── run_backend.py              # Server runner script
├── frontend/
│   ├── css/
│   │   └── styles.css              # Global styles & Glassmorphism theme
│   ├── js/
│   │   ├── main.js                 # Core frontend logic
│   │   ├── chat.js                 # Chat handling
│   │   ├── tasks.js                # Kanban board logic
│   │   └── calendar.js             # Timeline view logic
│   └── index.html                  # Main application entry
├── data/                           # Local database and vector store
├── requirements.txt                # Python dependencies
└── README.md
```

---

## 🔄 Workflow

### System Architecture
```mermaid
graph TD
    A[User Interface] -->|HTTP/WebSocket| B[FastAPI Backend]
    B -->|Query| C[SQLite Database]
    B -->|Vector Search| D[Knowledge Base]
    B -->|Prompt| E[Local LLM (Phi-3)]
    E -->|Response| B
    B -->|JSON/Stream| A
```

### Magic Schedule Flow
1. **Task Collection**: Aggregates pending tasks from the Kanban board.
2. **Constraint Analysis**: Checks existing calendar events and user preferences.
3. **AI Optimization**: Local LLM generates an optimal schedule.
4. **Allocation**: Tasks are assigned specific time slots in the database.
5. **Visualization**: The Calendar view updates in real-time.

---

## 🔌 API Endpoints

### `POST /api/chat`
Send a message to the AI assistant.
```json
{
  "message": "Plan my day based on my tasks",
  "context": "..."
}
```

### `GET /api/tasks`
Retrieve all tasks for the Kanban board.

### `POST /api/schedule/auto-assign`
Trigger the Magic Schedule algorithm to organize your day.

---

## 👥 Development Team

| Team Member | Role | GitHub |
|-------------|------|--------|
| **Rakshak D** | Lead Developer | [@Rakshak-D](https://github.com/Rakshak-D) |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🔮 Future Roadmap

- [ ] **Voice Interface**: Full STT/TTS integration for hands-free operation.
- [ ] **Mobile App**: React Native mobile application.
- [ ] **Plugin System**: Allow third-party integrations (Spotify, Notion, etc.).
- [ ] **Multi-User Support**: Collaborative workspaces and shared calendars.

---

**Experience the future of productivity with AURA. 🌌**

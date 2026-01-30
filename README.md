# Phoenix AI Agent

<p align="center">
  <a href="https://github.com/graviton711/Phoenix-Agent/releases"><img src="https://img.shields.io/github/v/release/graviton711/Phoenix-Agent?style=for-the-badge&color=blue" alt="GitHub Release"></a>
  <img src="https://img.shields.io/badge/AI_Models-8+-green?style=for-the-badge" alt="8+ AI Models">
  <img src="https://img.shields.io/badge/RAG_Engine-Hybrid-purple?style=for-the-badge" alt="Hybrid RAG">
  <img src="https://img.shields.io/badge/python-3.12-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12">
  <a href="https://github.com/graviton711/Phoenix-Agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/graviton711/Phoenix-Agent?style=for-the-badge&color=green" alt="License"></a>
</p>

<p align="center">
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React 18"></a>
  <a href="https://github.com/graviton711/Phoenix-Agent/stargazers"><img src="https://img.shields.io/github/stars/graviton711/Phoenix-Agent?style=flat-square&logo=github" alt="GitHub stars"></a>
</p>

An advanced multi-agent AI platform with RAG, MCP integration, and autonomous UI generation capabilities.

<p align="center">
  <img src="assets/branding.png" alt="Phoenix AI Agent" width="800">
</p>

## What's New in v2.0

### Double-Strike Reasoning Engine

The flagship feature is the **2-Stage Reasoning Pipeline** - an AI-powered intent detection system that routes requests to specialized agents for maximum accuracy.

```
+----------------------------------------------------------------------------------------+
|  PHOENIX AGENT - INTELLIGENT ORCHESTRATION                                             |
+----------------------------------------------------------------------------------------+
|                                                                                        |
|  STAGE 1: INTENT DETECTION (Llama 4 Scout)                                             |
|     Analyzes user message for:                                                         |
|       • Search Intent → Web Intelligence Engine                                        |
|       • Code Intent → Python Interpreter                                               |
|       • UI Build Intent → Architect + Analyst Agents                                   |
|       • Vision Intent → Gemma 3 Vision                                                 |
|       • Memory Intent → ChromaDB RAG                                                   |
|                                                                                        |
|  STAGE 2: MAIN RESPONSE (Qwen 32B)                                                     |
|     Synthesizes all context into:                                                      |
|       • Streaming markdown response                                                    |
|       • Code artifacts with live preview                                               |
|       • Automatic memory archival                                                      |
|                                                                                        |
|  SUPPORTED TOOLS:                                                                      |
|     [Search] [Code] [UI Build] [Vision] [RAG] [MCP Filesystem]                         |
|                                                                                        |
+----------------------------------------------------------------------------------------+
```

### How the Pipeline Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. USER REQUEST                                                │
│     "Search for the latest AI news and summarize"               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. INTENT DETECTOR (Llama 4 Scout - 500ms avg)                 │
│     • Flags: search=true, code=false, ui=false                  │
│     • Routes to: Web Intelligence Engine                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. SPECIALIZED AGENT EXECUTION                                 │
│     • DuckDuckGo Multi-Query Search                             │
│     • AI Reranking (Compound Mini)                              │
│     • Deep Content Summarization (Kimi K2)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. MAIN RESPONSE SYNTHESIS (Qwen 32B)                          │
│     Context + RAG Memory → Streaming Response → Memory Archival │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Model Architecture

Phoenix utilizes specialized models for each task:

| Component | Model ID | Purpose |
|-----------|----------|---------|
| **Orchestrator** | `meta-llama/llama-4-scout` | Intent detection & tool routing |
| **Core Intelligence** | `qwen/qwen3-32b` | Main reasoning & conversational response |
| **Vision Engine** | `gemma-3-27b-it` | Image analysis & text extraction |
| **UI Architect** | `google/gemini-3-flash` | React component generation |
| **Archivist** | `moonshotai/kimi-k2` | Long-term memory archival |
| **Code Expert** | `moonshotai/kimi-k2` | Documentation & code explanations |
| **Search Queries** | `openai/gpt-oss-120b` | Query optimization |
| **Knowledge Reranker** | `groq/compound-mini` | Search result scoring |
| **Embeddings** | `text-embedding-004` | Vector embeddings for RAG |

## Features

- **8+ AI Models** - Specialized models for each task type
- **Hybrid RAG** - Vector Search (ChromaDB) + BM25 with Reciprocal Rank Fusion
- **MCP Integration** - Model Context Protocol for filesystem & tool access
- **Multi-Modal Vision** - Image/PDF analysis via Gemma 3 Vision
- **Autonomous UI Builder** - Full React project generation from prompts
- **Self-Healing DB** - Automatic corruption detection and recovery
- **Global Memory** - Cross-session long-term memory with topic routing

<details>
<summary><b>Core Capabilities (7)</b></summary>

| # | Capability | Description |
|---|------------|-------------|
| 1 | **Web Intelligence** | Real-time search via DuckDuckGo with AI reranking |
| 2 | **Code Interpreter** | Safe Python execution for math/logic problems |
| 3 | **UI Generation** | Multi-file React projects from single prompt |
| 4 | **Vision Analysis** | Image OCR and diagram understanding |
| 5 | **RAG Memory** | Hybrid vector+keyword retrieval system |
| 6 | **MCP Tools** | Filesystem operations, GitHub integration |
| 7 | **Self-Reflection** | Automatic mindset updates from user feedback |

</details>

<details>
<summary><b>Supported Tech Stacks</b></summary>

| Category | Technologies |
|----------|--------------|
| **Frontend** | React 18, Vite, TypeScript, Tailwind CSS, Framer Motion |
| **Backend** | Python 3.12+, FastAPI, Uvicorn |
| **Infrastructure** | MCP, Docker Support |
| **Database** | ChromaDB (Vector), Firebase (NoSQL - Optional) |

</details>

## Installation

### Prerequisites
- Python 3.12+
- Node.js 18+
- API Keys: `GROQ_API_KEY`, `GOOGLE_API_KEY`

### 1. One-Click Setup (Windows)

```powershell
.\setup_env.bat
```

### 2. Manual Installation

**Backend:**
```bash
# Clone repository
git clone https://github.com/graviton711/Phoenix-Agent.git
cd Phoenix-Agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Create .env with GROQ_API_KEY, GOOGLE_API_KEY

# Start server
python src/api_server.py
```

**Frontend:**
```bash
cd phoenix-ai-chat-ui
npm install
npm run dev
```

## Usage

### Chat Naturally

Just describe what you need:

```
Search for the latest AI research papers on RAG

Build a landing page for my SaaS product

Analyze this image and extract all text

Create a dashboard for tracking metrics
```

### How It Works

1. **You ask** - Natural language request
2. **Intent Detection** - Llama 4 Scout analyzes and routes
3. **Specialized Agents** - Execute search, code, vision, or UI tasks
4. **Synthesis** - Qwen 32B combines all context into response
5. **Memory** - Important information archived for future sessions

## Project Structure

```
Phoenix-Agent/
├── phoenix-ai-chat-ui/    # Frontend React Application
├── src/                   # Backend Python Engine
│   ├── api_server.py      # FastAPI Main Entry (Gateway)
│   ├── config.py          # Central Model Configuration
│   ├── core/              # Core Logic
│   │   └── ai_core.py     # Multi-Model Adapter
│   ├── modules/           # Specialized Modules
│   │   ├── search_engine.py   # Agentic Search Pipeline
│   │   ├── document_rag.py    # Hybrid RAG Engine
│   │   ├── ui_builder.py      # Automated UI Factory
│   │   └── file_processor.py  # Vision & PDF Processing
│   ├── integrations/      # External Connections
│   │   └── mcp_client.py      # MCP Protocol Implementation
│   └── data/              # Static & Dynamic Data
│       └── topics.json        # Memory Topic Routing
├── prompts/               # Engineering System Prompts
├── workspace/             # AI-Generated Builds & File Storage
├── requirements.txt       # Python Dependencies
└── setup_env.bat          # Windows Auto-Setup Script
```

## Configuration

Create a `.env` file in the root directory:

```env
# Required
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=AIzaSy...

# Optional
FIREBASE_SERVICE_ACCOUNT={"type": "service_account", ...}
```

## Branding & Aesthetic

Phoenix AI follows a **"Deep Tech / Amber Obsidian"** design language:
- Glassmorphism with subtle amber accents
- High-contrast accessibility (WCAG AA)
- Smooth micro-animations (150-300ms)

> "To rise from the ashes is to evolve. Phoenix AI doesn't just answer; it builds."

## License

This project is licensed under the [MIT License](LICENSE).

---

*© 2025 Phoenix Intelligent Systems. Built with passion for the future.*

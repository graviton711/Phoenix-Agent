"""
Phoenix AI Chat Backend API
Powered by Groq (Qwen 32B)
"""
import sys
from pathlib import Path
# Ensure src directory is in path for uvicorn reloader
sys.path.insert(0, str(Path(__file__).parent))

import os
import shutil
import json
import re
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from modules.ui_builder import AppBuilder
from config import MAIN_MODEL_ID, TOOL_DETECTION_MODEL, EMBEDDING_MODEL
from modules.file_processor import process_file, get_file_type, generate_summary
from modules.document_rag import (
    index_uploaded_file, 
    retrieve_relevant_chunks, 
    has_indexed_documents,
    get_file_hash,
    cleanup_session_documents
)

# --- CLIENT ---
from groq import Groq
import firebase_admin
from firebase_admin import credentials, firestore

# --- MCP CLIENT ---
try:
    from integrations.mcp_client import get_mcp_manager, initialize_mcp_servers
    MCP_AVAILABLE = True
except ImportError:
    print("WARN: MCP client not found. MCP tools disabled.")
    MCP_AVAILABLE = False

# Init Env
load_dotenv()

# --- IMPORTS FOR RAG ---
# --- IMPORTS FOR RAG ---
# google.generativeai removed in favor of google-genai in ai_core.py
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("WARN: chromadb not found. RAG will be disabled.")
    chromadb = None

# --- CONFIG ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# Dirs (Absolute paths relative to root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")

# Gemini Keys for RAG
raw_gemini_keys = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEYS = [k.strip() for k in raw_gemini_keys.split(",") if k.strip()]

class KeyManager:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.index = 0
    
    def get_key(self) -> str:
        if not self.keys: return ""
        k = self.keys[self.index]
        self.index = (self.index + 1) % len(self.keys)
        return k

key_manager = KeyManager(GOOGLE_API_KEYS)

# --- RAG / MEMORY MANAGER ---
# --- RAG / MEMORY MANAGER ---
from core.ai_core import MemoryManager, MindsetManager

memory_manager = MemoryManager()
mindset_manager = MindsetManager()

MODEL_ID = MAIN_MODEL_ID

# --- FIREBASE ---
db = None
try:
    if not firebase_admin._apps:
        fb_creds = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if fb_creds:
            cred = credentials.Certificate(json.loads(fb_creds))
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("INFO: Firebase connected.")
    else:
        db = firestore.client()
except Exception as e:
    print(f"WARN: Firebase init error: {e}")

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan (startup/shutdown)."""
    # Startup: Initialize MCP
    if MCP_AVAILABLE:
        try:
            await initialize_mcp_servers()
            print("INFO: MCP servers initialized.")
        except Exception as e:
            print(f"WARN: Failed to initialize MCP servers: {e}")
    
    yield
    # Shutdown logic (if needed) can go here

# --- APP ---
app = FastAPI(title="Phoenix Chat Qwen", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STATIC FILE SERVING FOR LIVE PREVIEW ---
_builds_path = os.path.join(WORKSPACE_DIR, "builds")
if os.path.exists(_builds_path):
    app.mount("/preview", StaticFiles(directory=_builds_path, html=True), name="preview")
    print(f"INFO: Static preview mounted at /preview from {_builds_path}")

# --- STATIC FILE SERVING FOR UPLOADS ---
UPLOAD_DIR = os.path.join(WORKSPACE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
print(f"INFO: Static uploads mounted at /uploads from {UPLOAD_DIR}")

# --- MCP STARTUP REMOVED (Moved to lifespan) ---

# --- MODELS ---
class Message(BaseModel):
    id: str
    role: str
    content: str
    reasoning: Optional[str] = None
    timestamp: str

class ChatSession(BaseModel):
    id: str
    messages: List[Message] = []
    title: str = "New Chat"

class UserProfile(BaseModel):
    id: str = "owner"
    name: str = "Boss"
    avatar: str = "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix"
    isDarkMode: bool = True
    accentColor: str = "#d97706"

# --- IN MEMORY ---
sessions: Dict[str, ChatSession] = {}

# --- PROMPT ---
def load_system_prompt():
    try:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_main.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "You are a helpful AI."

# Using dynamic prompt for Mindset
def get_system_prompt():
    base = load_system_prompt()
    mindset = mindset_manager.get_mindset()
    if mindset:
        return f"{base}\n\n[MINDSET & SELF-EVOLUTION]:{mindset}"
    return base

# --- TOOL DETECTION (Stage 1) ---
TOOL_DETECTION_MODEL = TOOL_DETECTION_MODEL

def load_tool_detect_prompt():
    try:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_tool_detect.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Respond with JSON: {\"action\": \"none\", \"params\": {}}"

TOOL_DETECT_PROMPT = load_tool_detect_prompt()

async def detect_tool_intent(user_message: str, context: str = "") -> Dict[str, Any]:
    """
    Stage 1: Use llama-4-scout to detect which tool (if any) to use.
    Returns JSON like: {"action": "search", "params": {"query": "..."}}
    """
    try:
        messages = [
            {"role": "system", "content": TOOL_DETECT_PROMPT},
        ]
        if context:
            messages.append({"role": "system", "content": f"Recent context: {context}"})
        messages.append({"role": "user", "content": user_message})
        
        response = client.chat.completions.create(
            model=TOOL_DETECTION_MODEL,
            messages=messages,
            temperature=0.1,
            max_completion_tokens=256,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        # Validate action
        valid_actions = ["search", "python", "build", "file", "update_mindset", "save_knowledge", "none"]
        if result.get("action") not in valid_actions:
            result["action"] = "none"
            result["params"] = {}
        
        return result

        
    except json.JSONDecodeError as e:
        logger.error(f"Tool detection JSON error: {e}")
        return {"action": "none", "params": {}}
    except Exception as e:
        logger.error(f"Tool detection error: {e}")
        return {"action": "none", "params": {}}


def sanitize_math_output(text: str) -> str:
    """
    Remove duplicate plain-text fallback that appears right after LaTeX.
    Example: "$x^2 + y^2$x2 + y2" -> "$x^2 + y^2$"
    """
    # Pattern: $...$followed_by_text_without_space_that_looks_like_math
    # We look for LaTeX blocks followed immediately by plain text duplicates
    import re
    # Match $...$ followed by a similar looking plain text (no caret, just numbers)
    pattern = r'(\$[^\$]+\$)([a-zA-Z0-9\s\+\-\*\/\=\(\)\,\.]+?)(?=\s*[\:\.\,\n]|$)'
    
    def clean_match(m):
        latex = m.group(1)
        possibly_dupe = m.group(2).strip()
        # Check if the "dupe" looks like simplified version of latex (no ^, no $)
        latex_content = latex.strip('$').replace('^', '').replace('_', '').replace('{', '').replace('}', '').replace(' ', '')
        dupe_clean = possibly_dupe.replace(' ', '')
        
        # If they're very similar, it's likely a fallback -> remove it
        if len(dupe_clean) > 2 and dupe_clean in latex_content or latex_content in dupe_clean:
            return latex
        return m.group(0)
    
    return re.sub(pattern, clean_match, text)

# --- TOOLS ---
from ddgs import DDGS
from modules.search_engine import search_engine
import subprocess
import tempfile

async def async_web_search(query: str, max_results: int = 3, callback: Optional[Callable[[str], None]] = None) -> str:
    """Performs an advanced web search with AI-powered reranking and summarization."""
    try:
        from modules.search_engine import search_engine
        # Use the advanced search engine for better results
        result = await search_engine.search_and_rerank(query, initial_fetch=10, top_k=max_results, stream_callback=callback)
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        # Fallback to basic search if advanced fails
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    return "No results found."
                formatted = []
                for r in results:
                    formatted.append(f"Source: {r['href']}\nTitle: {r['title']}\nSnippet: {r['body']}")
                return "\n".join(formatted)
        except Exception as e2:
            return f"Search utterly failed: {str(e2)}"

def execute_python(code: str) -> str:
    """Executes Python code in a subprocess and returns output/error."""
    # Aggressively clean markers, headings, and bold titles
    code = code.strip()
    
    # FIX: Handle literal \n escape sequences that might leak from JSON-stringified AI outputs
    code = code.replace('\\n', '\n').replace('\\t', '\t')
    
    # Remove markers
    code = code.replace("```python", "").replace("```", "")
    
    # Filter out common AI-generated meta-text (headers, bold titles, etc.)
    lines = [l for l in code.split('\n') if l.strip()]
    clean_lines = []
    for line in lines:
        s = line.strip()
        # Skip if it looks like a title or a non-code description
        if s.startswith('#') or (s.startswith('**') and s.endswith('**')) or s.startswith('Tính '):
            continue
        clean_lines.append(line)
    
    final_code = "\n".join(clean_lines).strip()
    
    if not final_code:
        return f"Error: No valid Python code found. (Attempted to parse:\n{code[:100]}...)"

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
        # Prepend recursion limit increase to avoid stack overflow for recursive code
        safe_header = "import sys; sys.setrecursionlimit(5000)\n"
        tmp.write(safe_header + final_code)
        tmp_path = tmp.name

    try:
        # Run with a 10-second timeout
        result = subprocess.run(
            ["python", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8"
        )
        
        if result.returncode != 0:
            err_msg = result.stderr.strip() if result.stderr else "(Không có thông báo lỗi - có thể do stack overflow hoặc crash)"
            return f"PYTHON ERROR (Exit Code {result.returncode}):\n{err_msg}\n\nAttempted Code:\n```python\n{final_code}\n```"
            
        output = result.stdout.strip()
        return output if output else "Code executed (no output). Tip: Use `print()` to see results."
    except subprocess.TimeoutExpired:
        return "Error: Execution timed out (max 10s)."
    except Exception as e:
        return f"Execution error: {str(e)}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

async def execute_mcp_file(action: str, path: str, content: str = "") -> str:
    """Execute file operations via MCP Filesystem server."""
    if not MCP_AVAILABLE:
        return "Error: MCP not available. File operations disabled."
    
    try:
        manager = await get_mcp_manager()
        
        # Normalize path - ensure it's within workspace and strip whitespace/newlines
        path = path.strip().replace("\r", "").replace("\n", "")
        workspace_path = os.path.join(WORKSPACE_DIR, path.lstrip("/\\"))
        
        action_lower = action.lower().strip()
        
        if action_lower == "read":
            result = await manager.call_tool("read_file", {"path": workspace_path})
            if result is None:
                return f"Error reading file: No response from MCP"
            if "error" in result:
                return f"Error reading file: {result.get('error', 'Unknown error')}"
            # Extract content from result
            contents = result.get("content", [])
            if isinstance(contents, list):
                texts = []
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(c.get("text", ""))
                return "\n".join(texts) if texts else str(result)
            return str(contents) if contents else str(result)
            
        elif action_lower == "write":
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(workspace_path), exist_ok=True)
            result = await manager.call_tool("write_file", {"path": workspace_path, "content": content})
            if result is None:
                return f"Error writing file: No response from MCP"
            if "error" in result:
                return f"Error writing file: {result.get('error', 'Unknown error')}"
            return f"File written successfully: {path}"
            
        elif action_lower == "list":
            result = await manager.call_tool("list_directory", {"path": workspace_path})
            if result is None:
                return f"Error listing directory: No response from MCP"
            if "error" in result:
                return f"Error listing directory: {result.get('error', 'Unknown error')}"
            contents = result.get("content", [])
            if isinstance(contents, list):
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        return c.get("text", str(result))
            return str(result)
            
        elif action_lower == "search":
            result = await manager.call_tool("search_files", {"path": str(WORKSPACE_DIR), "pattern": path})
            if result is None:
                return f"Error searching files: No response from MCP"
            if "error" in result:
                return f"Error searching files: {result.get('error', 'Unknown error')}"
            contents = result.get("content", [])
            if isinstance(contents, list):
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        return c.get("text", str(result))
            return str(result)
            
        else:
            return f"Unknown file action: {action}. Available: read, write, list, search"
            
    except Exception as e:
        return f"MCP file operation error: {str(e)}"

async def build_ui_project(prompt: str, project_name: str = "phoenix_app", callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Invokes the UI Builder module to generate a multi-file web app. Returns structured data."""
    try:
        from modules.ui_builder import AppBuilder
        builder = AppBuilder(project_name)
        
        # Call builder.build directly as it is async
        results = await builder.build(prompt, stream_callback=callback)
        
        files = results.get("files", results.get("files_map", {}))
        return {
            "success": True,
            "project_name": results["project_name"],
            "project_path": results["project_path"],
            "files_map": files,
            "modified_files": list(files.keys())
        }
    except Exception as e:
        logger.error(f"Build failed: {e}")
        return {"success": False, "error": str(e)}

async def execute_update_mindset(operation: str, match: str = "", content: str = "") -> str:
    """Handler for update_mindset tool - allows Qwen to update its own mindset."""
    try:
        mindset_path = os.path.join(WORKSPACE_DIR, "mindset", "general.md")
        os.makedirs(os.path.dirname(mindset_path), exist_ok=True)
        
        # Read current mindset
        try:
            with open(mindset_path, "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
        except FileNotFoundError:
            lines = []
        
        op = operation.upper()
        
        if op == "ADD":
            if content and content not in lines:
                lines.append(content)
                with open(mindset_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                return f"✓ Mindset updated: Added '{content[:50]}...'"
            return "Rule already exists or empty content."
        
        elif op == "DELETE":
            for i, line in enumerate(lines):
                if match.strip() in line or line.strip() in match:
                    removed = lines.pop(i)
                    with open(mindset_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines))
                    return f"✓ Mindset updated: Removed '{removed[:50]}...'"
            return f"Rule not found: {match[:50]}"
        
        elif op == "MODIFY":
            for i, line in enumerate(lines):
                if match.strip() in line or line.strip() in match:
                    old = lines[i]
                    lines[i] = content
                    with open(mindset_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines))
                    return f"✓ Mindset updated: '{old[:30]}' → '{content[:30]}'"
            return f"Rule not found: {match[:50]}"
        
        return f"Unknown operation: {operation}"
    except Exception as e:
        return f"Mindset update failed: {e}"

async def execute_save_knowledge(content: str, topic: str) -> str:
    """Handler for save_knowledge tool - allows Qwen to save to vector DB."""
    try:
        result = await memory_manager.add_knowledge(content)
        return f"✓ Knowledge saved: {result}"
    except Exception as e:
        return f"Knowledge save failed: {e}"

def clean_tool_tags(text: str) -> str:
    """Removes artifacts, tool tags, and emojis from the text."""
    if not text: return ""
    # Remove tool tags (with brackets)
    text = re.sub(r'\[SEARCH:\s*.*?\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[BUILD:\s*.*?\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[PYTHON:\s*[\s\S]*?\]', '', text, flags=re.IGNORECASE)
    
    # FILE tags - aggressive cleanup for all variations
    # Complete tags with brackets
    text = re.sub(r'\[FILE:\s*[^\]]*\]', '', text, flags=re.IGNORECASE)
    # Tags with JSON content
    text = re.sub(r'\[FILE:[\s\S]*?(?:\}\]|\]\}|\])', '', text, flags=re.IGNORECASE)
    # Incomplete tags (no closing bracket) - match until end of line or start of text
    text = re.sub(r'\[FILE:\s*(?:read|write|list|search)\|[^\]\n]*(?=\n|Dưới|$)', '', text, flags=re.IGNORECASE)
    # Tags with backticks around them
    text = re.sub(r'`+\[FILE:[^\]`]*\]?`*', '', text, flags=re.IGNORECASE)
    # Raw FILE: commands without brackets  
    text = re.sub(r'FILE:\s*(?:read|write|list|search)\|[^\n]+', '', text, flags=re.IGNORECASE)
    
    # Remove raw SEARCH commands
    text = re.sub(r'SEARCH:\s*[^\n\[\]]+', '', text, flags=re.IGNORECASE)

    # Remove "Đang tìm kiếm:" phrases that leak
    text = re.sub(r'>\s*Đang tìm kiếm[:\s]*[^\n]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Đang tìm kiếm[:\s]*"?[^"\n]+"?\s*(năm\s*\d+)?', '', text, flags=re.IGNORECASE)
    # Remove artifacts: [B], [Build], [Start], [thought]
    text = re.sub(r"\[[Bb]uild\]|\[[Bb]\]|\[[Ss]tart\]|\[[Tt]hought\]", "", text)
    # Remove leading brackets/noise
    text = re.sub(r"^\s*\[+B*\s*", "", text)
    # Specific cleanup for leaked reasoning
    text = text.replace("> Đang thực thi mã Python...", "").replace("> Đang tìm kiếm...", "")
    # Remove common technical hallucinations
    text = text.replace("вывод kết quả:", "").replace("вывод:", "").replace("Output:", "")
    # Remove literal \n sequences that leak as text
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove emojis
    emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)
    text = emoji_pattern.sub("", text)
    return text.strip()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "build_ui_project",
            "description": "Build a full-scale, multi-file web application (UI) based on a detailed prompt. Use this for complex web projects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "A detailed description of the app to build."},
                    "project_name": {"type": "string", "description": "The name of the project folder (slug)."}
                },
                "required": ["prompt", "project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search for real-time information, news, facts, or technical documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_mindset",
            "description": "Update your internal mindset/preferences based on user feedback or corrections. Use this when the user tells you how they prefer you to behave.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["ADD", "DELETE", "MODIFY"], "description": "ADD=new rule, DELETE=remove rule, MODIFY=change existing rule"},
                    "match": {"type": "string", "description": "(For DELETE/MODIFY) The existing rule text to find."},
                    "content": {"type": "string", "description": "(For ADD/MODIFY) The new rule content, starting with '- '."}
                },
                "required": ["operation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_knowledge",
            "description": "Save important information to your long-term memory. Use this when the user teaches you something worth remembering for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The knowledge/fact to save."},
                    "topic": {"type": "string", "description": "The category: coding, general, politics, literature, etc."}
                },
                "required": ["content", "topic"]
            }
        }
    }
]

# --- LOGIC ---

async def stream_chat_generator(user_message: str, session_id: str):

    # 1. Setup Session
    if session_id not in sessions:
        sessions[session_id] = ChatSession(id=session_id)
    session = sessions[session_id]

    # 2. Build Messages
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_context = f"Dữ liệu thời gian hệ thống: {current_time_str}. Hãy dùng thông tin này để trả lời các câu hỏi về 'bây giờ', 'hôm nay' hoặc thời gian thực."
    
    # 3. Sliding Window & RAG
    msgs = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "system", "content": time_context}
    ]
    
    # 3.5 Document RAG: Retrieve relevant chunks
    rag_parts = []
    
    # Check Hot Buffer (immediate perception for just-uploaded files)
    if session_id in recent_uploads_cache:
        for f in recent_uploads_cache[session_id]:
            # For images, we just pass the whole description as they are small
            # For PDFs, it might be large, but let's take a summary or first part
            if f['file_type'] == 'image':
                rag_parts.append(f"[Hot Context - Recent Image: {f['file_name']}]:\n{f['text']}\n(Lưu ý: Đây là nội dung hình ảnh bạn vừa gửi, hãy dùng nó để trả lời.)")
            else:
                rag_parts.append(f"[Hot Context - Recent File: {f['file_name']}]:\n{f['text'][:2000]}")

    # Merge with indexed RAG results
    if has_indexed_documents(session_id):
        doc_context = await retrieve_relevant_chunks(session_id, user_message, top_k=5)
        if doc_context:
            rag_parts.append(doc_context)

    if rag_parts:
        msgs.append({"role": "system", "content": "\n\n---\n\n".join(rag_parts)})

    # Save User Msg (do this early for message ID)
    user_msg_id = str(uuid.uuid4())
    user_msg_obj = Message(
        id=user_msg_id,
        role="user",
        content=user_message,
        timestamp=datetime.now().isoformat()
    )
    session.messages.append(user_msg_obj)

    try:
        yield "data: " + json.dumps({'sessionId': session_id, 'type': 'start'}) + "\n\n"
        
        # === STAGE 1: Unified Tool Detection + RAG Decision ===
        recent_context = " | ".join([m.content[:100] for m in session.messages[-4:] if m.content])
        
        # Add hint about indexed files to help tool router decide
        if has_indexed_documents(session_id):
            recent_context = f"[HINT: A file is attached to this session] | {recent_context}"
        
        yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Analyzing intent...'}) + "\n\n"
        tool_intent = await detect_tool_intent(user_message, recent_context)
        
        action = tool_intent.get("action", "none")
        params = tool_intent.get("params", {})
        needs_rag = tool_intent.get("needs_rag", True) # Default to True for safety
        topic = tool_intent.get("topic", "general")
        
        # === Conditional Memory RAG (OPTIMIZED: Skip if not needed) ===
        if needs_rag:

            rag_context = await memory_manager.query_memory(user_message, topic_hint=topic)
            if rag_context:
                msgs.append({"role": "system", "content": f"Sử dụng thông tin bổ sung từ lịch sử trò chuyện nếu cần thiết: {rag_context}"})


        # Sliding Window: Take only last 12 messages for immediate context
        history_window = session.messages[-12:]
        for m in history_window:
            content = (m.content or "").strip()
            if not content and not m.reasoning: continue
            if m.role == "assistant":
                 if content: msgs.append({"role": "assistant", "content": content})
            else:
                 msgs.append({"role": "user", "content": content})
                 
        msgs.append({"role": "user", "content": user_message})
        
        # Async index user message (pass topic hint for efficient routing)
        asyncio.create_task(memory_manager.add_message(session_id, user_msg_id, "user", user_message, topic_hint=topic))
        
        # NOTE: Mindset reflection is now handled by Qwen via update_mindset tool
        # No automatic reflection call needed anymore

        tool_result = None

        
        # === Execute Tool if needed ===
        if action != "none":
            yield "data: " + json.dumps({'type': 'reasoning', 'delta': '\n> Tool detected: ' + action + '\n'}) + "\n\n"
            
            if action == "search":
                query = params.get("query", user_message)
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Searching: ' + query + '...\n'}) + "\n\n"
                
                # Streaming callback for search
                stream_queue = asyncio.Queue()
                def sync_cb(text: str):
                    stream_queue.put_nowait(text)
                
                # Run search in background task
                search_task = asyncio.create_task(async_web_search(query, callback=sync_cb))
                
                while not search_task.done() or not stream_queue.empty():
                    try:
                        chunk = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
                        if chunk.startswith("[SEARCH]"):
                            # Filter or format the search delta for UI
                            delta = chunk[8:]
                            if delta:
                                yield "data: " + json.dumps({'type': 'reasoning', 'delta': delta + '\n'}) + "\n\n"
                        else:
                            yield "data: " + json.dumps({'type': 'reasoning', 'delta': chunk + '\n'}) + "\n\n"
                    except asyncio.TimeoutError:
                        if search_task.done(): break
                        continue
                
                tool_result = await search_task
                
            elif action == "python":
                code = params.get("code", "")
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Executing Python...\n'}) + "\n\n"
                tool_result = await asyncio.to_thread(execute_python, code)
                yield "data: " + json.dumps({'type': 'execution_result', 'delta': tool_result + '\n'}) + "\n\n"
                
            elif action == "build":
                project_name = params.get("project_name", "phoenix_app")
                description = params.get("description", "")
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '\n> Building UI: ' + project_name + '...\n'}) + "\n\n"
                
                # Streaming callback for the build process
                def build_stream_callback(text: str):
                    # Local sync function to put tasks in the loop? 
                    # Simpler for SSE: we can't easily yield from a nested thread if we use to_thread,
                    # but since we made build_ui_project async, we can just call it!
                    pass

                # NEW: Using a lambda or wrapper that we'll handle inside build_ui_project
                # Actually, the easiest way is to pass a queue or use a specialized channel.
                # But for this SSE generator, we can just define a helper.
                
                async def sse_callback(text: str):
                    if text.startswith("[SPEC]"):
                        # Extract spec content and send as reasoning
                        delta = text[6:]
                        if delta:
                            await asyncio.sleep(0) # Yield control
                            # We can't yield from this nested async function to the parent generator easily
                            # without a queue.
                            pass

                # RE-RE-ACT: Let's use a simpler approach. We will call build_ui_project 
                # and pass a callback that writes to a shared list that we periodicially yield?
                # No, let's just make the callback print to logger for now IF we can't yield.
                
                # WAIT! I can just use a Queue.
                stream_queue = asyncio.Queue()
                def sync_cb(text: str):
                    stream_queue.put_nowait(text)
                
                # Run build in background task
                build_task = asyncio.create_task(build_ui_project(description, project_name, callback=sync_cb))
                
                while not build_task.done() or not stream_queue.empty():
                    try:
                        # Wait for either a chunk or the task to finish
                        # Use a timeout so we don't block forever if task dies
                        chunk = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
                        if chunk.startswith("[SPEC]"):
                            yield "data: " + json.dumps({'type': 'reasoning', 'delta': chunk[6:]}) + "\n\n"
                        else:
                            yield "data: " + json.dumps({'type': 'reasoning', 'delta': chunk}) + "\n\n"
                    except asyncio.TimeoutError:
                        if build_task.done(): break
                        continue
                
                build_result = await build_task
                
                if build_result.get("success"):
                    for filename, content in build_result['files_map'].items():
                        yield f"data: {json.dumps({'type': 'build_file_progress', 'filename': filename, 'content': content, 'projectName': build_result['project_name']})}\n\n"
                        await asyncio.sleep(0.1)
                    yield f"data: {json.dumps({'type': 'tool_build_result', 'projectName': build_result['project_name'], 'files': build_result['files_map']})}\n\n"
                    tool_result = f"SUCCESS: Project '{build_result['project_name']}' created. Files: {', '.join(build_result['modified_files'])}"
                else:
                    tool_result = f"BUILD ERROR: {build_result.get('error', 'Unknown error')}"
                    
            elif action == "file":
                file_type = params.get("type", "list")
                path = params.get("path", ".")
                content = params.get("content", "")
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> MCP File: ' + file_type + ' ' + path + '...\n'}) + "\n\n"
                tool_result = await execute_mcp_file(file_type, path, content)
                yield "data: " + json.dumps({'type': 'execution_result', 'delta': tool_result + '\n'}) + "\n\n"
        
            elif action == "update_mindset":
                operation = params.get("operation", "ADD")
                match = params.get("match", "")
                content = params.get("content", "")
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Updating mindset...'}) + "\n\n"
                tool_result = await execute_update_mindset(operation, match, content)
            
            elif action == "save_knowledge":
                knowledge_content = params.get("content", "")
                topic = params.get("topic", "general")
                yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Saving to memory...'}) + "\n\n"
                tool_result = await execute_save_knowledge(knowledge_content, topic)

        # === STAGE 2: Response Generation (using Qwen, streaming) ===
        # Build messages for response
        if tool_result:
            msgs.append({"role": "system", "content": f"Tool result ({action}):\n{tool_result}\n\nNow respond naturally to the user based on this result. Do NOT use any tool tags like [FILE:], [SEARCH:], etc."})
        
        max_turns = 3  # Reduced since tool detection is now separate
        turn = 0
        final_reasoning = ""
        final_content = ""
        full_text = ""

        while turn < max_turns:
            turn += 1
            full_text = "" 
            is_tool_triggered = False  # Legacy, kept for compatibility
            tool_query = ""
            tool_type = ""
            sent_reasoning_len = 0
            sent_content_len = 0

            try:
                response = client.chat.completions.create(
                    model=MODEL_ID, 
                    messages=msgs,
                    temperature=0.4 if turn == 1 else 0.2,
                    max_completion_tokens=4096,
                    top_p=0.9,
                    stream=True,
                    stop=None
                    # NO response_format for smooth streaming!
                )
                
                for chunk in response:
                    delta = chunk.choices[0].delta
                    content_delta = delta.content or ""
                    reasoning_delta = getattr(delta, "reasoning", None) or ""
                    
                    full_text += content_delta
                    
                    if reasoning_delta:
                        # Direct reasoning field support
                        clean_reasoning = clean_tool_tags(reasoning_delta) if sent_reasoning_len == 0 else reasoning_delta
                        if clean_reasoning.strip() or reasoning_delta.strip():
                            yield "data: " + json.dumps({'type': 'reasoning', 'delta': clean_reasoning}) + "\n\n"
                            final_reasoning += clean_reasoning
                        sent_reasoning_len += len(reasoning_delta)
                        # WE DON'T BREAK OR CONTINUE, just in case there's ALSO content (unlikely but safe)

                    # 1. Tool Detection via Regex (Hybrid Streaming)
                    # Use [\s\S]*? to capture multi-line code including newlines
                    s_match = re.search(r'\[SEARCH:\s*([\s\S]*?)\]', full_text, re.IGNORECASE)
                    p_match = re.search(r'\[PYTHON:\s*([\s\S]*?)\]', full_text, re.IGNORECASE)
                    b_match = re.search(r'\[BUILD:\s*([^|]+?)\|([\s\S]*?)\]', full_text, re.IGNORECASE)
                    # MCP FILE tool: [FILE: action|path] or [FILE: action|path|content]
                    f_match = re.search(r'\[FILE:\s*([^|]+?)\|([^|\]]+?)(?:\|([^\]]*))?\]', full_text, re.IGNORECASE)
                    
                    if s_match:
                        tool_query = s_match.group(1).strip()
                        tool_type = "search"
                        is_tool_triggered = True
                        break
                    if p_match:
                        tool_query = p_match.group(1).strip()
                        tool_type = "python"
                        is_tool_triggered = True
                        break
                    if b_match:
                        tool_query = f"{b_match.group(1).strip()}|{b_match.group(2).strip()}"
                        tool_type = "build"
                        is_tool_triggered = True
                        break
                    if f_match:
                        action = f_match.group(1).strip()
                        path = f_match.group(2).strip()
                        content = f_match.group(3).strip() if f_match.group(3) else ""
                        tool_query = f"{action}|{path}|{content}"
                        tool_type = "file"
                        is_tool_triggered = True
                        break
                    
                    # 2. Stream text directly (Smooth Streaming)
                    # Look for <think>...</think> for reasoning
                    think_match = re.search(r'<think>(.*?)(</think>|$)', full_text, re.DOTALL)
                    if think_match:
                        val = think_match.group(1).strip()
                        if len(val) > sent_reasoning_len:
                            diff = val[sent_reasoning_len:]
                            # Reasoning is less sensitive but let's keep it clean
                            clean_diff = clean_tool_tags(diff) if sent_reasoning_len == 0 else diff
                            if clean_diff.strip() or diff.strip():
                                yield "data: " + json.dumps({'type': 'reasoning', 'delta': clean_diff}) + "\n\n"
                                final_reasoning += clean_diff
                            sent_reasoning_len = len(val)
                        
                        # Extract content AFTER </think> tag
                        if '</think>' in full_text:
                            post_think = full_text.split('</think>', 1)[1].strip()
                            
                            # Check if there's a tool call (or attempted tool call) anywhere in post_think
                            has_tool_call = bool(
                                re.search(r'\[BUILD', post_think, re.IGNORECASE) or
                                re.search(r'\[SEARCH', post_think, re.IGNORECASE) or
                                re.search(r'\[PYTHON', post_think, re.IGNORECASE)
                            )
                            
                            if has_tool_call:
                                pass
                            elif len(post_think) > sent_content_len:
                                diff = post_think[sent_content_len:]
                                if sent_content_len == 0 and len(post_think) < 10:
                                    pass
                                else:
                                    clean_diff = clean_tool_tags(diff) if sent_content_len == 0 else diff
                                    if clean_diff.strip() or diff.strip():
                                        yield "data: " + json.dumps({'type': 'content', 'delta': clean_diff}) + "\n\n"
                                        final_content += clean_diff
                                    sent_content_len = len(post_think)
                    
                    # Also try JSON-style parsing as fallback
                    r_match = re.search(r'"reasoning"\s*:\s*"(.*?)((?<!\\)"|$)', full_text, re.DOTALL)
                    if r_match and not think_match:
                        val = r_match.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                        if len(val) > sent_reasoning_len:
                            diff = val[sent_reasoning_len:]
                            yield "data: " + json.dumps({'type': 'reasoning', 'delta': diff}) + "\n\n"
                            final_reasoning += diff
                            sent_reasoning_len = len(val)
                    
                    # Content extraction (JSON-style)
                    c_match = re.search(r'"content"\s*:\s*"(.*?)((?<!\\)"|$)', full_text, re.DOTALL)
                    if c_match and not think_match:
                        val = c_match.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                        if len(val) > sent_content_len:
                            diff = val[sent_content_len:]
                            if not (final_content.strip().endswith(diff.strip()) and len(diff.strip()) > 2):
                                yield "data: " + json.dumps({'type': 'content', 'delta': diff}) + "\n\n"
                                final_content += diff
                            sent_content_len = len(val)
                    
                    # Fallback: If no <think> or JSON, stream raw text as content
                    if not think_match and not r_match and not c_match and full_text.strip():
                        if len(full_text) > sent_content_len:
                            diff = full_text[sent_content_len:]
                            
                            # START-OF-STREAM SANITIZATION:
                            if sent_content_len == 0 and len(full_text) < 10:
                                # Wait for more tokens to be sure about the artifact
                                pass
                            else:
                                clean_diff = clean_tool_tags(diff) if sent_content_len == 0 else diff
                                if clean_diff.strip() or diff.strip():
                                    yield "data: " + json.dumps({'type': 'content', 'delta': clean_diff}) + "\n\n"
                                    final_content += clean_diff
                                sent_content_len = len(full_text)

                if is_tool_triggered:
                    tool_result = ""
                    if tool_type == "search":
                        yield "data: " + json.dumps({'type': 'reasoning', 'delta': '\n> Đang tìm kiếm: ' + tool_query + '...\n'}) + "\n\n"
                        tool_result = await asyncio.to_thread(web_search, tool_query)
                    elif tool_type == "python":
                        yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Đang thực thi mã Python...\n'}) + "\n\n"
                        tool_result = await asyncio.to_thread(execute_python, tool_query)
                        sep = f"\n{'-'*20} [TURN {turn}] {'-'*20}\n" if turn > 1 else ""
                        yield "data: " + json.dumps({'type': 'execution_result', 'delta': sep + tool_result + '\n'}) + "\n\n"
                    elif tool_type == "build":
                        p_name, p_prompt = tool_query.split("|", 1)
                        yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> Khởi tạo module UI Builder: ' + p_name + '...\n'}) + "\n\n"
                        build_result = await asyncio.to_thread(build_ui_project, p_prompt.strip(), p_name.strip())
                        
                        if build_result.get("success"):
                            # Send progress for each file (for animation)
                            for filename, content in build_result['files_map'].items():
                                yield "data: " + json.dumps({'type': 'build_file_progress', 'filename': filename, 'content': content, 'projectName': build_result['project_name']}) + "\n\n"
                                import time; time.sleep(0.1)  # Small delay for visual effect
                            
                            # Send final structured build result
                            yield "data: " + json.dumps({'type': 'tool_build_result', 'projectName': build_result['project_name'], 'files': build_result['files_map']}) + "\n\n"
                            tool_result = f"SUCCESS: Project '{build_result['project_name']}' created. Files: {', '.join(build_result['modified_files'])}"
                        else:
                            tool_result = f"BUILD ERROR: {build_result.get('error', 'Unknown error')}"
                    elif tool_type == "file":
                        # MCP File operation
                        parts = tool_query.split("|", 2)
                        action = parts[0] if len(parts) > 0 else ""
                        path = parts[1] if len(parts) > 1 else ""
                        content = parts[2] if len(parts) > 2 else ""
                        yield "data: " + json.dumps({'type': 'reasoning', 'delta': '> MCP File: ' + action + ' ' + path + '...\n'}) + "\n\n"
                        tool_result = await execute_mcp_file(action, path, content)
                        yield "data: " + json.dumps({'type': 'execution_result', 'delta': sep + tool_result + '\n'}) + "\n\n"

                    msgs.append({"role": "assistant", "content": full_text})
                    msgs.append({"role": "user", "content": f"KẾT QUẢ {tool_type.upper()}:\n\n{tool_result}\n\nLƯU Ý: Nếu kết quả có lỗi hoặc chưa đạt yêu cầu, hãy tự sửa lỗi bằng cách gọi lại công cụ hoặc trả lời trực tiếp."})

                    continue
                else:
                    break

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Turn {turn} failed: {str(e)}'})}\n\n"
                break

        # 4. Final Processing & Fallback
        if not final_reasoning and not final_content:
            # Fallback: If we didn't parse anything via streaming, try final parse
            think_m = re.search(r'<think>(.*?)</think>', full_text, re.DOTALL)
            if think_m:
                final_reasoning = think_m.group(1).strip()
            
            # Try to get content after </think> or from JSON
            post_think = re.sub(r'<think>.*?</think>', '', full_text, flags=re.DOTALL).strip()
            if post_think:
                final_content = post_think

        if final_reasoning and not sent_reasoning_len: 
            yield f"data: {json.dumps({'type': 'reasoning', 'delta': final_reasoning})}\n\n"
        if final_content and not sent_content_len: 
            yield f"data: {json.dumps({'type': 'content', 'delta': final_content})}\n\n"
        
        # Ultimate fallback: if we still have no content but have full_text, use it
        if not final_content and full_text:
            # Clean up any reasoning tags and use remainder
            cleaned_text = re.sub(r'<think>.*?</think>', '', full_text, flags=re.DOTALL).strip()
            if cleaned_text:
                yield f"data: {json.dumps({'type': 'content', 'delta': clean_tool_tags(cleaned_text)})}\n\n"
                final_content = cleaned_text

        # 5. Finish & Persist
        final_content = clean_tool_tags(sanitize_math_output(final_content))
        assistant_msg_id = str(uuid.uuid4())
        assistant_msg = Message(
            id=assistant_msg_id,
            role="assistant",
            content=final_content,
            reasoning=final_reasoning,
            timestamp=datetime.now().isoformat()
        )
        session.messages.append(assistant_msg)
        
        # Async index assistant message
        asyncio.create_task(memory_manager.add_message(session_id, assistant_msg_id, "assistant", final_content))
        
        yield f"data: {json.dumps({'type': 'done', 'messageId': assistant_msg_id})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        print(f"Master generator error: {e}")


@app.get("/api/chat/stream")
async def chat_stream(message: str, sessionId: Optional[str] = None):
    if not sessionId: sessionId = str(uuid.uuid4())
    return StreamingResponse(
        stream_chat_generator(message, sessionId), 
        media_type="text/event-stream"
    )

# --- PROFILE & MISC ---
@app.get("/api/profile")
def get_profile():
    if db:
        try:
            doc = db.collection("settings").document("profile").get()
            if doc.exists: return {"profile": doc.to_dict()}
        except: pass
    return {"profile": UserProfile().model_dump()}

@app.post("/api/profile")
def update_profile(p: UserProfile):
    if db:
        try:
            db.collection("settings").document("profile").set(p.model_dump())
        except: pass
    return {"success": True}

@app.get("/api/sessions")
def list_sessions():
    return {"sessions": [s.model_dump() for s in sessions.values()]}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": sessions[session_id].model_dump()}

@app.post("/api/sessions/new")
def create_session():
    new_id = str(uuid.uuid4())
    new_session = ChatSession(id=new_id, title="Đoạn chat mới")
    sessions[new_id] = new_session
    return {"session": new_session.model_dump()}

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        # Clean up session documents
        cleanup_session_documents(session_id)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Session not found")

# --- PROJECT MANAGEMENT API ---
from pathlib import Path
import shutil

@app.get("/api/projects")
def list_projects():
    """List all built projects in workspace/builds"""
    projects = []
    builds_path = os.path.join(WORKSPACE_DIR, "builds")
    if os.path.exists(builds_path):
        for name in os.listdir(builds_path):
            project_path = os.path.join(builds_path, name)
            if os.path.isdir(project_path):
                # Count files
                file_count = sum(1 for _ in Path(project_path).rglob("*") if _.is_file())
                if file_count == 0:
                    continue  # Skip empty projects
                projects.append({
                    "name": name,
                    "file_count": file_count,
                    "created_at": os.path.getctime(project_path)
                })
    return {"projects": sorted(projects, key=lambda x: x["created_at"], reverse=True)}

@app.get("/api/projects/{project_name}")
def get_project(project_name: str):
    """Load all files from a built project"""
    project_path = os.path.join(WORKSPACE_DIR, "builds", project_name)
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail="Project not found")
    
    files = {}
    for filepath in Path(project_path).rglob("*"):
        if filepath.is_file():
            rel_path = str(filepath.relative_to(project_path)).replace("\\", "/")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    files[rel_path] = f.read()
            except:
                pass  # Skip binary files
    return {"project_name": project_name, "files": files}

@app.delete("/api/projects/{project_name}")
def delete_project(project_name: str):
    """Delete a built project"""
    project_path = os.path.join(WORKSPACE_DIR, "builds", project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Project not found")

# --- FILE UPLOAD ---
# UPLOAD_DIR defined earlier for static mounting

# Track indexing status
indexing_status: Dict[str, dict] = {}  # file_hash -> {status, progress, error}
# Hot Buffer: {session_id: [{file_name, file_hash, text, file_type, timestamp}]}
recent_uploads_cache: Dict[str, List[dict]] = {}

async def _index_document_async(session_id: str, file_hash: str, file_name: str, text: str):
    """Background task for document indexing."""
    try:
        indexing_status[file_hash] = {"status": "indexing", "progress": 0}
        result = await index_uploaded_file(session_id, file_hash, file_name, text)
        indexing_status[file_hash] = {"status": "done", "result": result}
        
        # Cleanup Hot Buffer for this session once indexed
        if session_id in recent_uploads_cache:
            recent_uploads_cache[session_id] = [
                f for f in recent_uploads_cache[session_id] if f['file_hash'] != file_hash
            ]
    except Exception as e:
        indexing_status[file_hash] = {"status": "error", "error": str(e)}

@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    sessionId: Optional[str] = None
):
    """
    Upload and process a file (image or PDF).
    Starts async indexing for RAG retrieval.
    """
    try:
        # Save file temporarily
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Process file to get text
        file_type, extracted_text, file_bytes = await process_file(file_path)
        
        # Get file hash for caching
        file_hash = get_file_hash(file_bytes)
        
        # Start async indexing if session provided
        if sessionId:
            # Update Hot Buffer for immediate perception
            if sessionId not in recent_uploads_cache:
                recent_uploads_cache[sessionId] = []
            recent_uploads_cache[sessionId].append({
                "file_name": file.filename,
                "file_hash": file_hash,
                "text": extracted_text,
                "file_type": file_type,
                "timestamp": datetime.now()
            })
            
            # Keep only last 3 hot uploads to save memory
            recent_uploads_cache[sessionId] = recent_uploads_cache[sessionId][-3:]

            background_tasks.add_task(_index_document_async, sessionId, file_hash, file.filename, extracted_text)
        
        return {
            "success": True,
            "filename": file.filename,
            "file_type": file_type,
            "file_hash": file_hash,
            "previewUrl": f"http://localhost:8000/uploads/{file.filename}" if file_type == "image" else None,
            "indexing": sessionId is not None,
            # Don't send full text - just confirmation
            "text_length": len(extracted_text)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/upload/status/{file_hash}")
def get_indexing_status(file_hash: str):
    """Check indexing status for a file."""
    if file_hash in indexing_status:
        return indexing_status[file_hash]
    return {"status": "not_found"}

if __name__ == "__main__":


    import uvicorn
    # Use reload - use api_server directly since we're running from src/
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["src"])

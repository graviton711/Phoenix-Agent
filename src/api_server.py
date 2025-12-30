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

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from ui_builder import AppBuilder
from config import MAIN_MODEL_ID, TOOL_DETECTION_MODEL, EMBEDDING_MODEL

# --- CLIENT ---
from groq import Groq
import firebase_admin
from firebase_admin import credentials, firestore

# --- MCP CLIENT ---
try:
    from mcp_client import get_mcp_manager, initialize_mcp_servers
    MCP_AVAILABLE = True
except ImportError:
    print("WARN: MCP client not found. MCP tools disabled.")
    MCP_AVAILABLE = False

# Init Env
load_dotenv()

# --- IMPORTS FOR RAG ---
import google.generativeai as genai
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
class MemoryManager:
    def __init__(self, persist_directory: str = os.path.join(BASE_DIR, "chroma_db")):
        if not chromadb:
            self.client = None
            return
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name="chat_memory")

    async def get_embedding(self, text: str) -> List[float]:
        key = key_manager.get_key()
        if not key: return []
        try:
            genai.configure(api_key=key)
            # Using find_model to be safe although gemini-embedding-001 is standard
            result = await asyncio.to_thread(
                genai.embed_content,
                model=EMBEDDING_MODEL, # text-embedding-004 is gemini-embedding-001
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception as e:
            print(f"ERROR: Embedding failed: {e}")
            return []

    async def add_message(self, session_id: str, msg_id: str, role: str, content: str):
        if not self.client or not content.strip(): return
        emb = await self.get_embedding(content)
        if not emb: return
        
        self.collection.add(
            ids=[msg_id],
            embeddings=[emb],
            metadatas=[{"session_id": session_id, "role": role, "timestamp": datetime.now().isoformat()}],
            documents=[content]
        )

    async def query_memory(self, session_id: str, query_text: str, top_k: int = 3) -> str:
        if not self.client or not query_text.strip(): return ""
        query_emb = await self.get_embedding(query_text)
        if not query_emb: return ""
        
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k
            # Removed session_id filter to enable Global cross-chat memory
        )
        
        docs = results.get("documents", [[]])[0]
        if not docs: return ""
        
        context = "\n---\n".join(docs)
        return f"\n[BỐI CẢNH LỊCH SỬ LIÊN QUAN]:\n{context}\n"

memory_manager = MemoryManager()

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

# --- APP ---
app = FastAPI(title="Phoenix Chat Qwen")

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

# --- MCP STARTUP ---
@app.on_event("startup")
async def startup_event():
    """Initialize MCP servers on startup."""
    if MCP_AVAILABLE:
        try:
            await initialize_mcp_servers()
            print("INFO: MCP servers initialized.")
        except Exception as e:
            print(f"WARN: Failed to initialize MCP servers: {e}")

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

SYSTEM_PROMPT = load_system_prompt()

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
        valid_actions = ["search", "python", "build", "file", "none"]
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
from duckduckgo_search import DDGS
from search_engine import search_engine
import subprocess
import tempfile

async def async_web_search(query: str, max_results: int = 3, callback: Optional[Callable[[str], None]] = None) -> str:
    """Performs an advanced web search with AI-powered reranking and summarization."""
    try:
        from search_engine import search_engine
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
        from ui_builder import AppBuilder
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
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": time_context}
    ]

    # Get relevant context from RAG
    rag_context = await memory_manager.query_memory(session_id, user_message)
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
    
    # Save User Msg
    user_msg_id = str(uuid.uuid4())
    user_msg_obj = Message(
        id=user_msg_id,
        role="user",
        content=user_message,
        timestamp=datetime.now().isoformat()
    )
    session.messages.append(user_msg_obj)
    
    # Async index user message
    asyncio.create_task(memory_manager.add_message(session_id, user_msg_id, "user", user_message))

    try:
        yield f"data: {json.dumps({'sessionId': session_id, 'type': 'start'})}\n\n"
        
        # === STAGE 1: Tool Detection (using llama-4-scout) ===
        # Get recent context for tool detection
        recent_context = " | ".join([m.content[:100] for m in session.messages[-4:] if m.content])
        
        yield f"data: {json.dumps({'type': 'reasoning', 'delta': '> Analyzing intent...'})}\n\n"
        tool_intent = await detect_tool_intent(user_message, recent_context)
        
        tool_result = None
        action = tool_intent.get("action", "none")
        params = tool_intent.get("params", {})
        
        # === Execute Tool if needed ===
        if action != "none":
            yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'\\n> Tool detected: {action}\\n'})}\n\n"
            
            if action == "search":
                query = params.get("query", user_message)
                yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'> Searching: {query}...\\n'})}\n\n"
                
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
                                yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'{delta}\n'})}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'{chunk}\n'})}\n\n"
                    except asyncio.TimeoutError:
                        if search_task.done(): break
                        continue
                
                tool_result = await search_task
                
            elif action == "python":
                code = params.get("code", "")
                yield f"data: {json.dumps({'type': 'reasoning', 'delta': '> Executing Python...\\n'})}\n\n"
                tool_result = await asyncio.to_thread(execute_python, code)
                yield f"data: {json.dumps({'type': 'execution_result', 'delta': tool_result + '\\n'})}\n\n"
                
            elif action == "build":
                project_name = params.get("project_name", "phoenix_app")
                description = params.get("description", "")
                yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'\\n> Building UI: {project_name}...\\n'})}\n\n"
                
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
                            yield f"data: {json.dumps({'type': 'reasoning', 'delta': chunk[6:]})}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'reasoning', 'delta': chunk})}\n\n"
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
                yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'> MCP File: {file_type} {path}...\\n'})}\n\n"
                tool_result = await execute_mcp_file(file_type, path, content)
                yield f"data: {json.dumps({'type': 'execution_result', 'delta': tool_result + '\\n'})}\n\n"
        
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
                            yield f"data: {json.dumps({'type': 'reasoning', 'delta': clean_reasoning})}\n\n"
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
                                yield f"data: {json.dumps({'type': 'reasoning', 'delta': clean_diff})}\n\n"
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
                                        yield f"data: {json.dumps({'type': 'content', 'delta': clean_diff})}\n\n"
                                        final_content += clean_diff
                                    sent_content_len = len(post_think)
                    
                    # Also try JSON-style parsing as fallback
                    r_match = re.search(r'"reasoning"\s*:\s*"(.*?)((?<!\\)"|$)', full_text, re.DOTALL)
                    if r_match and not think_match:
                        val = r_match.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                        if len(val) > sent_reasoning_len:
                            diff = val[sent_reasoning_len:]
                            yield f"data: {json.dumps({'type': 'reasoning', 'delta': diff})}\n\n"
                            final_reasoning += diff
                            sent_reasoning_len = len(val)
                    
                    # Content extraction (JSON-style)
                    c_match = re.search(r'"content"\s*:\s*"(.*?)((?<!\\)"|$)', full_text, re.DOTALL)
                    if c_match and not think_match:
                        val = c_match.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                        if len(val) > sent_content_len:
                            diff = val[sent_content_len:]
                            if not (final_content.strip().endswith(diff.strip()) and len(diff.strip()) > 2):
                                yield f"data: {json.dumps({'type': 'content', 'delta': diff})}\n\n"
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
                                    yield f"data: {json.dumps({'type': 'content', 'delta': clean_diff})}\n\n"
                                    final_content += clean_diff
                                sent_content_len = len(full_text)

                if is_tool_triggered:
                    tool_result = ""
                    if tool_type == "search":
                        yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'\\n> Đang tìm kiếm: {tool_query}...\\n'})}\n\n"
                        tool_result = await asyncio.to_thread(web_search, tool_query)
                    elif tool_type == "python":
                        yield f"data: {json.dumps({'type': 'reasoning', 'delta': '> Đang thực thi mã Python...\\n'})}\n\n"
                        tool_result = await asyncio.to_thread(execute_python, tool_query)
                        sep = f"\n{'-'*20} [TURN {turn}] {'-'*20}\n" if turn > 1 else ""
                        yield f"data: {json.dumps({'type': 'execution_result', 'delta': sep + tool_result + '\n'})}\n\n"
                    elif tool_type == "build":
                        p_name, p_prompt = tool_query.split("|", 1)
                        yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'> Khởi tạo module UI Builder: {p_name}...\\n'})}\n\n"
                        build_result = await asyncio.to_thread(build_ui_project, p_prompt.strip(), p_name.strip())
                        
                        if build_result.get("success"):
                            # Send progress for each file (for animation)
                            for filename, content in build_result['files_map'].items():
                                yield f"data: {json.dumps({'type': 'build_file_progress', 'filename': filename, 'content': content, 'projectName': build_result['project_name']})}\n\n"
                                import time; time.sleep(0.1)  # Small delay for visual effect
                            
                            # Send final structured build result
                            yield f"data: {json.dumps({'type': 'tool_build_result', 'projectName': build_result['project_name'], 'files': build_result['files_map']})}\n\n"
                            tool_result = f"SUCCESS: Project '{build_result['project_name']}' created. Files: {', '.join(build_result['modified_files'])}"
                        else:
                            tool_result = f"BUILD ERROR: {build_result.get('error', 'Unknown error')}"
                    elif tool_type == "file":
                        # MCP File operation
                        parts = tool_query.split("|", 2)
                        action = parts[0] if len(parts) > 0 else ""
                        path = parts[1] if len(parts) > 1 else ""
                        content = parts[2] if len(parts) > 2 else ""
                        yield f"data: {json.dumps({'type': 'reasoning', 'delta': f'> MCP File: {action} {path}...\\n'})}\n\n"
                        tool_result = await execute_mcp_file(action, path, content)
                        yield f"data: {json.dumps({'type': 'execution_result', 'delta': tool_result + '\\n'})}\n\n"

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
    return StreamingResponse(stream_chat_generator(message, sessionId), media_type="text/event-stream")

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

if __name__ == "__main__":
    import uvicorn
    # Use reload - use api_server directly since we're running from src/
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["src"])

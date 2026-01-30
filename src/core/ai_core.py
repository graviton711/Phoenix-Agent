import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Load key strictly from environment variable
# Load key strictly from environment variable
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GOOGLE_API_KEYS = os.getenv('GOOGLE_API_KEY', '').split(',')

from google import genai
from google.genai import types
import random
import json

class KeyManager:
    def __init__(self, keys):
        self.keys = [k.strip() for k in keys if k.strip()]
        self.index = 0
    
    def get_key(self):
        if not self.keys: return None
        # Simple round-robin
        key = self.keys[self.index]
        self.index = (self.index + 1) % len(self.keys)
        return key

key_manager = KeyManager(GOOGLE_API_KEYS)

class GenAIChunkAdapter:
    def __init__(self, chunk):
        # Handle both Groq and Google chunks if needed, but currently Google streams differently.
        # For strict compatibility, we might need adjustments if we use streaming with Google.
        self.text = chunk.choices[0].delta.content or "" 

class GenAIResponseAdapter:
    def __init__(self, resp):
        # Check if it's a Groq response or Google response
        if hasattr(resp, 'choices'):
            self.text = resp.choices[0].message.content
        elif hasattr(resp, 'text'):
            self.text = resp.text
        else:
            self.text = ""

class GoogleGenAIAdapter:
    def __init__(self):
        self.models = self # compatibility hack
    
    def generate_content(self, model, contents, **kwargs):
        from google.api_core import exceptions
        
        # Determine max retries based on available keys
        max_retries = len(key_manager.keys) if key_manager.keys else 1
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Configure Key for this request (or retry)
                api_key = key_manager.get_key()
                if not api_key: raise ValueError("No GOOGLE_API_KEY found")
                
                # Instantiate Client
                client = genai.Client(api_key=api_key)
                
                # Parse arguments
                call_kwargs = kwargs.copy()
                system_instruction = call_kwargs.pop('system_instruction', None)
                temperature = call_kwargs.pop('temperature', 0.7)
                response_format = call_kwargs.pop('response_format', None)
                
                # Build Config
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_instruction
                )
                
                if response_format:
                    if 'json_schema' in response_format:
                        config.response_mime_type = "application/json"
                        config.response_schema = response_format['json_schema']
                    elif response_format.get('type') == 'json_object':
                        config.response_mime_type = "application/json"

                # Call generate
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return GenAIResponseAdapter(resp)
                
            except Exception as e:
                # 429, 403, 500 handling implicit in catch-all for now
                last_exception = e
                print(f"[Warn] Key {api_key[:8]}... failed ({type(e).__name__}). Rotating to next key...")
                continue
        
        # If we exit loop, we failed
        raise last_exception if last_exception else RuntimeError("Failed to generate content after all retries")

    def generate_content_stream(self, model, contents, **kwargs):
        
        max_retries = len(key_manager.keys) if key_manager.keys else 1
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                api_key = key_manager.get_key()
                if not api_key: raise ValueError("No GOOGLE_API_KEY found")
                
                client = genai.Client(api_key=api_key)
                
                # Copy kwargs to preserve original args
                call_kwargs = kwargs.copy()
                system_instruction = call_kwargs.pop('system_instruction', None)
                temperature = call_kwargs.pop('temperature', 0.7)
                
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_instruction
                )

                # Enable streaming
                return client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config
                )
                
            except Exception as e:
                last_exception = e
                print(f"[Warn] Stream Key {api_key[:8]}... failed ({type(e).__name__}). Rotating...")
                continue
        
        raise last_exception if last_exception else RuntimeError("Failed to stream content after all retries")

class GroqAdapter:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.models = self # minimal hack to support client.models.generate_content
    
    def generate_content(self, model, contents, **kwargs):
        # contents can be a string or list.
        user_msg = contents
        if isinstance(contents, list):
             # Simple join if list
            user_msg = "\n".join([str(c) for c in contents])

        # Extract system prompt if present in kwargs (custom adapter logic)
        messages = []
        if 'system_instruction' in kwargs:
             messages.append({"role": "system", "content": kwargs.pop('system_instruction')})
        
        # Add user message
        messages.append({"role": "user", "content": user_msg})

        # Groq specific: Handle response_format if passed
        response_format = kwargs.pop('response_format', None)
        
        # Explicit filtering of unsupported parameters
        # Remove 'reasoning_format' and 'include_reasoning' if model is not Groq/supported
        # But here we assume caller handles it.
        # Actually, let's clean up kwargs to be safe.
        clean_kwargs = {k:v for k,v in kwargs.items() if k not in ['reasoning_format', 'include_reasoning']}
        # Re-add if we knew better, but for now safe default.
        # Or just pass kwargs as is?
        # The user was seeing 400 errors.
        # ui_builder.py now handles this, so we are good.
        
        resp = self.client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format,
            **kwargs
        )
        return GenAIResponseAdapter(resp)
    
    def generate_content_stream(self, model, contents, **kwargs):
        user_msg = contents
        if isinstance(contents, list):
            user_msg = "\n".join([str(c) for c in contents])
            
        messages = []
        if 'system_instruction' in kwargs:
             messages.append({"role": "system", "content": kwargs.pop('system_instruction')})
        
        messages.append({"role": "user", "content": user_msg})

        # Groq specific: Handle response_format if passed
        response_format = kwargs.pop('response_format', None)

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            response_format=response_format,
            **kwargs
        )
        return stream

def get_client(provider="groq"):
    if provider == "google":
        return GoogleGenAIAdapter()
    
    if not GROQ_API_KEY:
         # Fallback to Google if Groq missing but Google present?
         if GOOGLE_API_KEYS: return GoogleGenAIAdapter()
         raise ValueError("Thiếu GROQ_API_KEY")
    return GroqAdapter(api_key=GROQ_API_KEY)

# --- ADVANCED MEMORY & MINDSET ---
import chromadb
from datetime import datetime
import asyncio
from config import EMBEDDING_MODEL, ROUTER_MODEL, ARCHIVIST_MODEL, MINDSET_MODEL
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class MemoryManager:
    def __init__(self, persist_directory: str = os.path.join(BASE_DIR, "chroma_db")):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.default_collection = self.client.get_or_create_collection(name="general")
        
        # Load specialized topics/collections
        try:
            with open(os.path.join(BASE_DIR, "data", "topics.json"), "r") as f:
                self.topics = json.load(f)
        except:
            self.topics = ["coding", "general"]

        self.collections = {
            topic: self.client.get_or_create_collection(name=topic) 
            for topic in self.topics
        }

    def _create_new_topic(self, topic: str):
        """Dynamically registers a new topic."""
        if topic in self.topics: return
        print(f"INFO: Creating NEW Topic DB: [{topic}]")
        self.topics.append(topic)
        self.collections[topic] = self.client.get_or_create_collection(name=topic)
        # Persist
        try:
            with open(os.path.join(BASE_DIR, "data", "topics.json"), "w") as f:
                json.dump(self.topics, f, indent=2)
        except Exception as e:
            print(f"WARN: Failed to save topics.json: {e}")

    async def get_embedding(self, text: str):
        key = key_manager.get_key()
        if not key: return []
        try:
            client = genai.Client(api_key=key)
            result = await asyncio.to_thread(
                client.models.embed_content,
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            return result.embeddings[0].values
        except Exception as e:
            print(f"ERROR: Embedding failed: {e}")
            return []

    async def route_query(self, query: str) -> str:
        """Determines which topic collection to search."""
        sys_prompt = open(os.path.join(BASE_DIR, "prompts/sys_prompt_router.txt")).read().replace("[topics_list]", str(self.topics))
        client = get_client("groq") # Use fast model
        try:
            resp = client.generate_content(
                model=ROUTER_MODEL,
                contents=query,
                system_instruction=sys_prompt,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.text)
            return data.get("topic", "general")
        except:
            return "general"

    async def archive_content(self, content: str) -> dict:
        """Structures raw content into a knowledge chunk."""
        sys_prompt = open(os.path.join(BASE_DIR, "prompts/sys_prompt_archivist.txt")).read()
        client = get_client("groq") 
        try:
            from config import ARCHIVIST_MODEL_JSON
            resp = client.generate_content(
                model=ARCHIVIST_MODEL_JSON, 
                contents=content,
                system_instruction=sys_prompt,
                response_format={"type": "json_object"}
            )
            return json.loads(resp.text)
        except Exception as e:
            print(f"Archivist Error: {e}")
            return {"title": "Raw Memory", "tags": [], "summary": content[:50], "content": content}

    async def add_knowledge(self, content: str):
        """Intelligent addition: Archive -> Embed -> Store in correct topic."""
        chunk = await self.archive_content(content)
        
        # Route content to find where to store it.
        topic = await self.route_query(chunk['summary'])
        
        # Dynamic Topic Creation Check
        if topic not in self.topics:
            # Simple validation: alphabetic only, reasonable length
            if topic.isalpha() and len(topic) < 20:
                self._create_new_topic(topic)
            else:
                topic = "general"

        target_col = self.collections.get(topic, self.default_collection)
        
        emb = await self.get_embedding(chunk['content'])
        ids = str(uuid.uuid4())
        
        target_col.add(
            ids=[ids],
            embeddings=[emb],
            metadatas=[{
                "title": chunk['title'], 
                "tags": ",".join(chunk['tags']), 
                "timestamp": datetime.now().isoformat()
            }],
            documents=[chunk['content']]
        )
        return f"Saved to [{topic}]: {chunk['title']}"

    async def add_message(self, session_id: str, msg_id: str, role: str, content: str, topic_hint: str = None):
        """Fast path for chat history logging (bypasses Archivist, optionally bypasses Router with topic_hint)."""
        if not content.strip(): return
        
        # Use topic_hint if provided, otherwise route
        topic = topic_hint if topic_hint and topic_hint in self.topics else await self.route_query(content)
        
        # Dynamic Topic Creation for Chat
        if topic not in self.topics:
            if topic.isalpha() and len(topic) < 20:
                self._create_new_topic(topic)
            else:
                topic = "general"
        
        target_col = self.collections.get(topic, self.default_collection)
        
        emb = await self.get_embedding(content)
        if not emb: return

        target_col.add(
            ids=[msg_id],
            embeddings=[emb],
            metadatas=[{"session_id": session_id, "role": role, "timestamp": datetime.now().isoformat()}],
            documents=[content]
        )

    async def query_memory(self, query_text: str, top_k: int = 3, topic_hint: str = None) -> str:
        # Use topic_hint if provided, otherwise route
        topic = topic_hint if topic_hint and topic_hint in self.topics else await self.route_query(query_text)
        target_col = self.collections.get(topic, self.default_collection)
        
        emb = await self.get_embedding(query_text)
        if not emb: return ""
        
        results = target_col.query(query_embeddings=[emb], n_results=top_k)
        docs = results.get("documents", [[]])[0]
        
        if not docs: return ""
        context = "\n---\n".join(docs)
        return f"\n[RAG Context - Topic: {topic}]:\n{context}\n"

class MindsetManager:
    def __init__(self):
        self.mindset_dir = os.path.join(BASE_DIR, "workspace", "mindset")
        os.makedirs(self.mindset_dir, exist_ok=True)
        # Init default if empty
        if not os.listdir(self.mindset_dir):
            with open(os.path.join(self.mindset_dir, "general.md"), "w") as f:
                f.write("- Always be helpful and precise.\n- Prioritize user intent.")

    def get_mindset(self) -> str:
        combined = ""
        for file in os.listdir(self.mindset_dir):
            if file.endswith(".md"):
                content = open(os.path.join(self.mindset_dir, file), encoding="utf-8").read()
                combined += f"\n[{file}]:\n{content}\n"
        return combined


    async def reflect_and_update(self, history: str):
        """Self-Correction loop with incremental updates."""
        sys_prompt = open(os.path.join(BASE_DIR, "prompts/sys_prompt_reflection.txt"), encoding="utf-8").read()
        current_mindset = self.get_mindset()
        
        client = get_client("groq")
        try:
            resp = client.generate_content(
                model=MINDSET_MODEL,
                contents=f"CURRENT MINDSET:\n{current_mindset}\n\nHISTORY:\n{history}",
                system_instruction=sys_prompt,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.text)
            
            if not data.get("update_needed"):
                return "No update needed."
            
            operations = data.get("operations", [])
            if not operations:
                return "No operations provided."
            
            # Read current mindset file
            mindset_path = os.path.join(self.mindset_dir, "general.md")
            try:
                with open(mindset_path, "r", encoding="utf-8") as f:
                    lines = f.read().strip().split("\n")
            except FileNotFoundError:
                lines = []
            
            changes_made = []
            
            for op in operations:
                op_type = op.get("op", "").upper()
                
                if op_type == "ADD":
                    content = op.get("content", "")
                    if content and content not in lines:
                        lines.append(content)
                        changes_made.append(f"+ADD: {content[:50]}")
                
                elif op_type == "DELETE":
                    match = op.get("match", "")
                    if match:
                        # Fuzzy match: find line containing the match text
                        for i, line in enumerate(lines):
                            if match.strip() in line or line.strip() in match:
                                changes_made.append(f"-DEL: {lines[i][:50]}")
                                lines.pop(i)
                                break
                
                elif op_type == "MODIFY":
                    match = op.get("match", "")
                    content = op.get("content", "")
                    if match and content:
                        for i, line in enumerate(lines):
                            if match.strip() in line or line.strip() in match:
                                changes_made.append(f"~MOD: {lines[i][:30]} -> {content[:30]}")
                                lines[i] = content
                                break
            
            # Write back
            if changes_made:
                with open(mindset_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                return f"Mindset updated: {', '.join(changes_made)}"
            
            return "No changes applied."
                
        except Exception as e:
            print(f"Reflection failed: {e}")
        return "Reflection error."

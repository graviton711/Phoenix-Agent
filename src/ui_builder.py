import os
import re
import json
import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable
from ai_core import get_client
from config import UI_ARCHITECT_MODEL, UI_DEFAULT_MODEL, UI_SCRIBE_MODEL

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("UI_Builder")

# --- CONSTANTS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
BUILD_DIR = os.path.join(BASE_DIR, "workspace", "builds")

# --- MODELS ---
# Using Gemini 3.0 Flash as requested
ARCHITECT_MODEL = UI_ARCHITECT_MODEL
DEFAULT_MODEL = UI_DEFAULT_MODEL

# Simplified Schema for One-Shot Builder
PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of the build"},
        "project_name": {"type": "string", "description": "Slug-friendly project name"},
        "build_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "Full source code content of the file"}
                },
                "required": ["file", "content"]
            }
        }
    },
    "required": ["summary", "project_name", "build_plan"]
}

class AppBuilder:
    """
    Phoenix UI Builder Module - JSON Edition
    Leverages Groq's Structured Outputs for bulletproof code generation.
    """
    
    def __init__(self, project_name: str = "phoenix_app"):
        self.project_name = project_name
        self.output_dir = os.path.join(BUILD_DIR, project_name)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Load Prompts
        self.system_prompt = self._load_sys_prompt()
        self.architect_prompt = self._load_architect_prompt()
        self.analyst_prompt = self._load_analyst_prompt()
        self.coder_prompt = self._load_coder_prompt()
        self.updater_prompt = self._load_updater_prompt()
        self.retriever_prompt = self._load_retriever_prompt()
        self.scribe_prompt = self._load_scribe_prompt()
        # Force Google Provider for main build
        self.client = get_client(provider="google")
        # Initialize Groq client for Scribe (Kimi)
        try:
            self.scribe_client = get_client(provider="groq")
        except:
            self.scribe_client = self.client # Fallback to Google if Groq fails
            
        logger.info(f"Initialized Unified Builder for: {project_name}")

    def _sanitize_text(self, text: str) -> str:
        """Removes AI artifacts, markdown code blocks, and emojis."""
        if not text: return ""
        
        # 0. Remove <think>...</think> blocks (reasoning residue)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL) # In case it's cut off
        
        # 1. Remove markdown code blocks (e.g. ```typescript ... ```)
        # Match ```language \n code \n ```
        text = re.sub(r"```[a-zA-Z0-9]*\n?", "", text)
        text = text.replace("```", "")
        
        # 2. Remove artifacts like [B], [Build], [Start], [thought] etc.
        text = re.sub(r"\[[Bb]uild\]|\[[Bb]\]|\[[Ss]tart\]|\[[Tt]hought\]", "", text)
        # Remove leading brackets/noise if still present
        text = re.sub(r"^\s*\[+B*\s*", "", text)
        
        # 3. Remove emojis (common range)
        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)
        text = emoji_pattern.sub("", text)
        
        return text.strip()

    def _load_sys_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_ui_gen.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Act as a senior React engineer. Output JSON."

    def _load_analyst_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_analyst.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Analyze the request and create a web app spec."

    def _load_architect_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_architect.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Plan the project structure. Output JSON."

    def _load_coder_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_coder.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Generate code for a single file."

    def _load_updater_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_updater.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Act as a Code Maintainer. Output JSON."

    def _load_retriever_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_retriever.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Select files. Output JSON."

    def _load_scribe_prompt(self) -> str:
        path = os.path.join(PROMPTS_DIR, "sys_prompt_scribe.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "Update README.md."

    def _get_file_tree(self) -> List[str]:
        all_files = []
        for root, _, filenames in os.walk(self.output_dir):
            for filename in filenames:
                if filename.endswith(('.html', '.css', '.js', '.jsx', '.ts', '.tsx', '.json')):
                    rel_path = os.path.relpath(os.path.join(root, filename), self.output_dir).replace("\\", "/")
                    all_files.append(rel_path)
        return all_files

    def _read_specific_files(self, file_paths: List[str]) -> str:
        context_parts = []
        for rel_path in file_paths:
            full_path = os.path.join(self.output_dir, rel_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        context_parts.append(f"--- FILE: {rel_path} ---\n{f.read()}\n\n")
                except Exception as e:
                    logger.error(f"Failed to read {rel_path}: {e}")
        return "".join(context_parts)

    async def _retrieve_relevant_files(self, user_prompt: str, file_tree: List[str]) -> List[str]:
        if not file_tree: return []
        tree_str = "\n".join([f"- {f}" for f in file_tree])
        
        # Read README for semantics
        readme_path = os.path.join(self.output_dir, "README.md")
        readme_content = ""
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    readme_content = f"CURRENT README:\n{f.read()}\n\n"
            except Exception as e: logger.warning(e)
        
        prompt = self.retriever_prompt + f"\n\nUSER PROMPT: {user_prompt}\n\nFILE TREE:\n{tree_str}\n\n"
        if readme_content: prompt = readme_content + prompt

        try:
            schema = {
                "type": "json_schema",
                "json_schema": {
                    "name": "file_selection",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "selected_files": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["selected_files"],
                        "additionalProperties": False
                    }
                }
            }
            response = await asyncio.to_thread(
                self.client.generate_content,
                model=DEFAULT_MODEL,
                contents=prompt,
                response_format=schema,
                temperature=0.0
            )
            data = json.loads(response.text)
            return data.get("selected_files", [])
        except Exception as e:
            logger.error(f"Librarian failed: {e}")
            return [f for f in file_tree if 'App' in f or 'main' in f]

    async def _update_readme(self, user_prompt: str, file_tree: List[str]):
        logger.info("Scribe: Updating README...")
        tree_str = "\n".join([f"- {f}" for f in file_tree])
        prompt = f"USER REQUEST: {user_prompt}\n\nFILE TREE:\n{tree_str}\n"
        try:
            # Use Kimi (Groq) for README
            # Kimi model ID moved to config.py
            SCRIBE_MODEL = UI_SCRIBE_MODEL 
            
            response = await asyncio.to_thread(
                self.scribe_client.generate_content,
                model=SCRIBE_MODEL,
                contents=prompt,
                system_instruction=self.scribe_prompt,
                temperature=0.5
            )
            new_readme = response.text
            with open(os.path.join(self.output_dir, "README.md"), 'w', encoding='utf-8') as f:
                f.write(new_readme)
        except Exception as e: logger.error(f"Scribe failed: {e}")

    async def _enrich_prompt(self, user_prompt: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        logger.info("Analyst: Enriching prompt...")
        if stream_callback: stream_callback("[SPEC]Drafting Technical Spec...\n")
        
        full_text = ""
        try:
            # We use the Analyst prompt here, expecting Markdown/Text (not JSON)
            stream = self.client.generate_content_stream(
                model=DEFAULT_MODEL,
                contents=user_prompt,
                system_instruction=self.analyst_prompt,
                temperature=0.7
            )
            
            for chunk in stream:
                text = chunk.text
                if text:
                    full_text += text
                    # Stream with [SPEC] prefix so frontend can route to "reasoning" panel
                    if stream_callback: stream_callback(f"[SPEC]{text}")

            spec = self._sanitize_text(full_text)
            if stream_callback: stream_callback("[SPEC]\n---\nSpec Ready!\n\n")
            return spec
        except Exception as e:
            logger.error(f"Analyst failed: {e}")
            return user_prompt


    async def build(self, user_prompt: str, stream_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        logger.info(f"Starting Multi-Model Build: {self.project_name}")
        file_tree = self._get_file_tree()
        is_fresh = not file_tree
        
        # Phase 0: Prompt Enrichment
        enriched_prompt = await self._enrich_prompt(user_prompt, stream_callback)
        
        # Phase 1: Planning (One-Shot Build)
        if stream_callback: stream_callback("Architect: Creating Build Plan...\\n\\n")
        context = ""
        if not is_fresh:
            relevant_files = await self._retrieve_relevant_files(enriched_prompt, file_tree)
            context = self._read_specific_files(relevant_files)
        
        planning_msg = f"USER REQUEST: {enriched_prompt}\n\nCONTEXT:\n{context}\n\nFILE TREE:\n{file_tree}"
        
        try:
            # One-Shot Builder with Gemini 3 Flash
            if stream_callback: stream_callback("Gemini 3 Flash: Building entire project in one shot...\\n")

            plan_response = await asyncio.to_thread(
                self.client.generate_content,
                model=ARCHITECT_MODEL,
                contents=planning_msg,
                system_instruction=self.architect_prompt,
                response_format={"json_schema": PROJECT_SCHEMA},
                temperature=0.2
            )
            
            plan_data = json.loads(plan_response.text)
            summary = plan_data.get("summary", "Building project...")
            build_plan = plan_data.get("build_plan", [])
            
            if stream_callback: stream_callback(f"**Plan Summary:** {summary}\\n\\n")
            
            # Process files directly
            files_map = {}
            for item in build_plan:
                filename = item.get('file')
                content = item.get('content') # Now expects content
                
                if filename and content:
                    # Sanitize and write
                    code = self._sanitize_text(content)
                    self._process_single_json_change({"file": filename, "action": "write", "content": code})
                    files_map[filename] = code
                    if stream_callback: stream_callback(f"Generated: `{filename}`\\n")

            # Update README
            all_files = list(set(list(files_map.keys()) + file_tree))
            await self._update_readme(user_prompt, all_files)
            
            if stream_callback: stream_callback(f"\\nBuild Complete! Total files: {len(files_map)}\\n")
            
            return {
                "project_path": self.output_dir,
                "project_name": self.project_name,
                "summary": summary,
                "files": files_map
            }
            
        except Exception as e:
            logger.error(f"Build failed: {e}")
            if stream_callback: stream_callback(f"Error: {str(e)}\\n")
            raise e

    def _process_single_json_change(self, change: Dict[str, str]) -> Optional[str]:
        try:
            filename = change.get("file")
            action = change.get("action")
            if not filename or not action: return None
            safe_name = re.sub(r'[\\*?:"<>|]', "", filename).replace("\\", "/").lstrip("/")
            path = os.path.join(self.output_dir, safe_name)
            
            if action == "write":
                content = change.get("content", "")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f: f.write(content)
                return safe_name
            elif action == "patch":
                s, r = change.get("search", ""), change.get("replace", "")
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f: curr = f.read()
                    if s in curr:
                        with open(path, 'w', encoding='utf-8') as f: f.write(curr.replace(s, r))
                        return safe_name
            return None
        except Exception as e:
            logger.error(f"Process failed: {e}")
            return None

    def _process_changes_json(self, text: str) -> Dict[str, str]:
        f_map = {}
        try:
            text = re.sub(r"```json", "", text).replace("```", "").strip()
            data = json.loads(text)
            for c in data.get("changes", []):
                name = c.get("file")
                if not name: continue
                safe = re.sub(r'[\\*?:"<>|]', "", name).replace("\\", "/").lstrip("/")
                
                # ALWAYS write to disk
                if c.get("action") == "write":
                    content = c.get("content", "")
                    path = os.path.join(self.output_dir, safe)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f: 
                        f.write(content)
                    f_map[safe] = content
                    logger.info(f"Saved file: {safe}")
                else:
                    p = os.path.join(self.output_dir, safe)
                    if os.path.exists(p):
                        with open(p, 'r', encoding='utf-8') as f: f_map[safe] = f.read()
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}. Response was: {text[:500]}...")
        except Exception as e:
            logger.error(f"Process changes failed: {e}")
        return f_map

if __name__ == "__main__":
    builder = AppBuilder("test_shop")
    async def run(): await builder.build("Create a react app")
    asyncio.run(run())

# --- Main Chat Model ---
MAIN_MODEL_ID = "qwen/qwen3-32b"

# --- Tool Detection (Stage 1) ---
TOOL_DETECTION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- RAG / Memory ---
EMBEDDING_MODEL = "models/text-embedding-004"

# --- UI Builder ---
UI_ARCHITECT_MODEL = "gemini-3-flash-preview"
UI_DEFAULT_MODEL = "gemini-3-flash-preview"
UI_SCRIBE_MODEL = "moonshotai/kimi-k2-instruct-0905"

# --- Search Engine Models ---
SEARCH_MODEL_FAST = "openai/gpt-oss-120b"
SEARCH_MODEL_MID = "groq/compound-mini"
SEARCH_MODEL_SMART = "moonshotai/kimi-k2-instruct"

# --- Advanced Agents ---
ROUTER_MODEL = "groq/compound-mini"
ARCHIVIST_MODEL = "moonshotai/kimi-k2-instruct"
ARCHIVIST_MODEL_JSON = "moonshotai/kimi-k2-instruct-0905" # Fallback for robust JSON
MINDSET_MODEL = "qwen/qwen3-32b"
VISION_MODEL = "gemma-3-27b-it" # For image processing (multimodal)

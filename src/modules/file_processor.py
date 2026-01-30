"""
File Processor Module
Handles image-to-text (via Gemma 3 Vision) and PDF-to-text (via PyMuPDF)
"""
import os
import base64
import asyncio
from typing import Optional, Tuple
from google import genai
from google.genai import types
from config import VISION_MODEL

# Get API keys
from dotenv import load_dotenv
load_dotenv()

raw_gemini_keys = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEYS = [k.strip() for k in raw_gemini_keys.split(",") if k.strip()]

class KeyRotator:
    def __init__(self, keys):
        self.keys = keys
        self.index = 0
    
    def get_key(self):
        if not self.keys: return ""
        k = self.keys[self.index]
        self.index = (self.index + 1) % len(self.keys)
        return k

key_rotator = KeyRotator(GOOGLE_API_KEYS)

async def process_image(image_path: str, prompt: str = "Describe this image in detail. Extract all text visible in the image.") -> str:
    """
    Process an image using Gemma 3 27B Vision model.
    Returns extracted text/description.
    """
    try:
        key = key_rotator.get_key()
        if not key:
            return "Error: No Google API key configured."
        
        client = genai.Client(api_key=key)
        
        # Read and encode image (Client handles bytes directly if using Part)
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # Determine MIME type
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        mime_type = mime_map.get(ext, "image/jpeg")
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=VISION_MODEL,
            contents=[
                prompt,
                types.Part.from_bytes(image_data, mime_type)
            ]
        )
        
        return response.text
        
    except Exception as e:
        return f"Image processing error: {str(e)}"


async def process_pdf(pdf_path: str, max_pages: int = 20) -> str:
    """
    Extract content from a PDF file as Markdown using pymupdf4llm.
    Returns structured markdown text.
    """
    try:
        import pymupdf4llm
        
        # Convert PDF to Markdown
        md_text = pymupdf4llm.to_markdown(pdf_path, pages=list(range(max_pages)))
        
        if not md_text.strip():
            return "PDF appears to be empty or contains only images."
        
        return md_text
        
    except ImportError:
        # Fallback to basic extraction if pymupdf4llm not installed
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for i, page in enumerate(doc):
                if i >= max_pages:
                    text_parts.append(f"\n[...Truncated at {max_pages} pages...]")
                    break
                
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(f"## Page {i+1}\n\n{page_text}")
            
            doc.close()
            
            if not text_parts:
                return "PDF appears to be empty or contains only images."
            
            return "\n\n---\n\n".join(text_parts)
            
        except ImportError:
            return "Error: PyMuPDF not installed. Run: pip install pymupdf pymupdf4llm"
    except Exception as e:
        return f"PDF processing error: {str(e)}"


def get_file_type(filename: str) -> str:
    """Determine if a file is an image, pdf, or unknown."""
    ext = os.path.splitext(filename)[1].lower()
    
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    pdf_exts = {".pdf"}
    
    if ext in image_exts:
        return "image"
    elif ext in pdf_exts:
        return "pdf"
    else:
        return "unknown"


def generate_summary(text: str, max_length: int = 500) -> str:
    """
    Generate a quick summary from the beginning of the text.
    Used for contextual prefix in RAG chunks.
    """
    # Simple extractive summary: first N characters up to sentence boundary
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    # Try to end at sentence boundary
    last_period = truncated.rfind('.')
    if last_period > max_length // 2:
        return truncated[:last_period + 1]
    return truncated + "..."


async def process_file(file_path: str, custom_prompt: Optional[str] = None) -> Tuple[str, str, bytes]:
    """
    Main entry point. Detects file type and processes accordingly.
    Returns (file_type, extracted_text, file_bytes)
    """
    # Read file bytes for hashing
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    
    file_type = get_file_type(file_path)
    
    if file_type == "image":
        prompt = custom_prompt or "Analyze this image. Extract all visible text and describe the content in detail."
        text = await process_image(file_path, prompt)
        return ("image", text, file_bytes)
    
    elif file_type == "pdf":
        text = await process_pdf(file_path)
        return ("pdf", text, file_bytes)
    
    else:
        return ("unknown", f"Unsupported file type: {os.path.splitext(file_path)[1]}", file_bytes)


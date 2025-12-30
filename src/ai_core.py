import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Load key strictly from environment variable
# Load key strictly from environment variable
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GOOGLE_API_KEYS = os.getenv('GOOGLE_API_KEY', '').split(',')

import google.generativeai as genai
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
                genai.configure(api_key=api_key)
                
                # Parse arguments (copy kwargs to avoid mutation issues across retries if any)
                # But here we pop, so we need to be careful. Ideally we prepare args outside loop.
                # However, to keep this patch simple, we assume kwargs are fresh or we reconstruct.
                # Actually, popping modifies kwargs. We should reconstruct it or use .get().
                # Let's reconstruct configuration inside the loop? No, that's inefficient.
                # Better: Parse once, then use inside.
                
                # RE-parsing logic to be safe across attempts:
                call_kwargs = kwargs.copy()
                system_instruction = call_kwargs.pop('system_instruction', None)
                temperature = call_kwargs.pop('temperature', 0.7)
                response_format = call_kwargs.pop('response_format', None)
                
                generation_config = {"temperature": temperature}
                if response_format:
                    if 'json_schema' in response_format:
                        generation_config["response_mime_type"] = "application/json"
                        generation_config["response_schema"] = response_format['json_schema']
                    elif response_format.get('type') == 'json_object':
                        generation_config["response_mime_type"] = "application/json"

                # Instantiate model
                gen_model = genai.GenerativeModel(
                    model_name=model,
                    system_instruction=system_instruction
                )
                
                # Call generate
                resp = gen_model.generate_content(
                    contents,
                    generation_config=generation_config
                )
                return GenAIResponseAdapter(resp)
                
            except (exceptions.ResourceExhausted, exceptions.PermissionDenied, exceptions.InternalServerError) as e:
                # 429, 403, 500
                last_exception = e
                print(f"[Warn] Key {api_key[:8]}... failed ({type(e).__name__}). Rotating to next key...")
                continue
            except Exception as e:
                # Unknown error, maybe don't retry? Or retry strictly for robustness?
                # Let's retry only on known Google API errors usually, but for "Antigravity" let's be aggressive.
                last_exception = e
                print(f"[Warn] Unexpected error with key {api_key[:8]}...: {e}. Rotating...")
                continue
        
        # If we exit loop, we failed
        raise last_exception if last_exception else RuntimeError("Failed to generate content after all retries")

    def generate_content_stream(self, model, contents, **kwargs):
        from google.api_core import exceptions
        
        max_retries = len(key_manager.keys) if key_manager.keys else 1
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                api_key = key_manager.get_key()
                if not api_key: raise ValueError("No GOOGLE_API_KEY found")
                genai.configure(api_key=api_key)
                
                # Copy kwargs to preserve original args
                call_kwargs = kwargs.copy()
                system_instruction = call_kwargs.pop('system_instruction', None)
                temperature = call_kwargs.pop('temperature', 0.7)
                
                generation_config = {"temperature": temperature}

                gen_model = genai.GenerativeModel(
                    model_name=model,
                    system_instruction=system_instruction
                )
                
                # Enable streaming
                return gen_model.generate_content(
                    contents,
                    generation_config=generation_config,
                    stream=True
                )
                
            except (exceptions.ResourceExhausted, exceptions.PermissionDenied, exceptions.InternalServerError) as e:
                last_exception = e
                print(f"[Warn] Stream Key {api_key[:8]}... failed ({type(e).__name__}). Rotating...")
                continue
            except Exception as e:
                last_exception = e
                print(f"[Warn] Stream error with key {api_key[:8]}...: {e}. Rotating...")
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

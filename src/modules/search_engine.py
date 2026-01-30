from typing import Optional, Callable, Dict, Any, List
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import json
import re
import os
from core.ai_core import get_client
from config import SEARCH_MODEL_FAST, SEARCH_MODEL_MID, SEARCH_MODEL_SMART

# Dirs
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")

class AdvancedSearch:
    def __init__(self):
        # PHÂN CHIA NHIỆM VỤ (Load Balancing để tiết kiệm token):
        self.model_fast = SEARCH_MODEL_FAST       # Query Gen (Siêu tốc, rẻ)
        self.model_mid = SEARCH_MODEL_MID        # Rerank & Summarize (Nhẹ nhàng)
        self.model_smart = SEARCH_MODEL_SMART # Logic chuyên sâu

    def load_query_prompt(self):
        try:
            path = os.path.join(PROMPTS_DIR, "sys_prompt_query.txt")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except:
            return "Convert user question to search keywords. Vietnamese focus."


    async def parse_url_content(self, url: str, session, timeout: int = 15):
        """
        Tải nội dung chi tiết từ URL (Crawling) vả làm sạch kỹ lưỡng (Async).
        """
        try:
            import aiohttp
            async with session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                # Get text
                try:
                    text = await response.text()
                except:
                    # Fallback for encoding issues
                    content_bytes = await response.read()
                    text = content_bytes.decode('utf-8', errors='ignore')

                # Parsing in thread to avoid blocking loop
                import asyncio
                clean_text = await asyncio.to_thread(self._clean_html, text)
                return clean_text
            
        except Exception as e:
            return "" # Return empty string on error

    def _clean_html(self, html_content: str) -> str:
        """Helper to clean HTML (CPU bound)"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 1. Decompose standard junk tags
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'iframe', 'noscript', 'ads', 'svg', 'button', 'form']):
                element.decompose()
            
            # 2. Decompose by common "junk" class/id names
            junk_selectors = [
                '.nav', '.menu', '.footer', '.header', '.sidebar', '.widget', '.ads', '.cookie', 
                '.popup', '.modal', '.banner', '.share', '.social', '.comment', '.related'
            ]
            for selector in junk_selectors:
                for element in soup.select(selector):
                    element.decompose()

            # 3. Get text with explicit separator
            text = soup.get_text(separator='\n')
            
            # 4. Collapse multiple newlines/spaces
            lines = (line.strip() for line in text.splitlines())
            # Chỉ giữ lại dòng có độ dài nhất định (tránh menu items rời rạc)
            clean_lines = [line for line in lines if len(line.split()) > 3 or len(line) > 20] 
            
            clean_text = '\n'.join(clean_lines)
            return clean_text[:3000] # Giảm xuống 3000 tokens để tránh Rate Limit Groq Free Tier
        except:
            return ""

    def generate_optimized_query(self, user_query: str) -> str:
        """
        Dùng model 20B để tạo từ khóa tiếng Việt tối ưu dựa trên bộ quy tắc trừu tượng.
        """
        sys_prompt = self.load_query_prompt()
        user_msg = f"Câu hỏi từ người dùng: \"{user_query}\"\n\nHãy tạo từ khóa tìm kiếm tối ưu nhất."

        try:
            client = get_client()
            response = client.models.generate_content(
                model=self.model_fast, 
                contents=sys_prompt + "\n\n" + user_msg,
            )
            optimized = response.text.strip().replace('"', '')
            print(f"QUERY OPTIMIZED ({self.model_fast}): '{user_query}' -> '{optimized}'")
            return optimized
        except Exception as e:
            print(f"QUERY GEN ERROR: {e}")
            return user_query

    def summarize_with_ai(self, content: str, query: str, source_title: str) -> str:
        """
        TÌNH BÁO VIÊN (Async): Đọc hiểu sâu và tóm tắt tiếng Việt.
        """
        try:
            path = os.path.join(PROMPTS_DIR, "sys_prompt_intel.txt")
            with open(path, 'r', encoding='utf-8') as f:
                sys_prompt = f.read()
        except:
            sys_prompt = "Tóm tắt các sự thật quan trọng bằng tiếng Việt."

        user_msg = f"Câu hỏi: {query}\n\nNội dung web:\n{content}"

        try:
            client = get_client()
            response = client.models.generate_content(
                model=self.model_mid, 
                contents=sys_prompt + "\n\n" + user_msg,
            )
            summary = response.text.strip()
            
            if "NO_RELEVANT_INFO" in summary:
                return None
                
            return f"NGUỒN: {source_title}\nBÁO CÁO TÌNH BÁO:\n{summary}\n"
        except Exception as e:
            print(f"INTEL AGENT ERROR: {e}")
            return None

    def call_gemma_rerank(self, query: str, results: list, top_k: int) -> list[int]:
        """
        TRỌNG TÀI (4B): Chấm điểm độ liên quan bằng tiếng Việt.
        """
        try:
            path = os.path.join(PROMPTS_DIR, "sys_prompt_rerank.txt")
            with open(path, 'r', encoding='utf-8') as f:
                sys_prompt_template = f.read()
        except FileNotFoundError:
            sys_prompt_template = "Chọn {top_k} kết quả tốt nhất ở định dạng JSON [0, 1, ...]."

        results_text = ""
        for i, r in enumerate(results):
            snippet = r['text'][:300].replace('\n', ' ') 
            results_text += f"[{i}] {snippet}\n"

        prompt = sys_prompt_template.replace("{top_k}", str(top_k))
        prompt = prompt.replace("{query}", query)
        prompt = prompt.replace("{results_text}", results_text)

        try:
            client = get_client()
            response = client.models.generate_content(
                model=self.model_mid,
                contents=prompt,
            )
            
            text = response.text.strip()
            match = re.search(r'\[[\d,\s]*\]', text)
            if match:
                indices = json.loads(match.group(0))
                return indices[:top_k]
            else:
                return list(range(top_k)) 
                
        except Exception as e:
            print(f"RERANK ERROR: {e}")
            return list(range(top_k))

    async def search_and_rerank(self, user_query: str, initial_fetch: int = 15, top_k: int = 3, stream_callback: Optional[Callable[[str], None]] = None):
        """
        Quy trình Search Async "Agentic" với Streaming Support.
        """
        import asyncio

        if stream_callback: stream_callback(f"[SEARCH]Tối ưu hóa từ khóa tìm kiếm...")
        # 1. Generate optimized query (Run in thread to avoid blocking)
        search_query = await asyncio.to_thread(self.generate_optimized_query, user_query)
        
        if stream_callback: stream_callback(f"[SEARCH]Đang tìm kiếm: {search_query}...")
        
        raw_results = []
        try:
            # DDGS is synchronous
            def run_ddgs():
                results = []
                with DDGS() as ddgs:
                    # Retry logic simple
                    ddg_gen = ddgs.text(search_query, region='vn-vi', max_results=initial_fetch)
                    for r in ddg_gen:
                        results.append({
                            "id": r.get('href'),
                            "text": f"{r.get('title')} - {r.get('body')}",
                            "meta": r
                        })
                return results

            raw_results = await asyncio.to_thread(run_ddgs)
            
            # Stream raw links immediately for visual feedback
            if stream_callback and raw_results:
                for r in raw_results[:8]: # Stream first 8 raw results to show activity
                    stream_callback(f"[SEARCH]FOUND:{r['meta']['href']}|{r['meta']['title']}")
            
        except Exception as e:
            return f"Search failed: {e}"

        if not raw_results:
            if stream_callback: stream_callback(f"[SEARCH]Không tìm thấy kết quả.")
            return "No results found."

        if stream_callback: stream_callback(f"[SEARCH]Đang xếp hạng {len(raw_results)} kết quả...")
        
        # 2. Rerank (Gemma 4B)
        selected_indices = await asyncio.to_thread(self.call_gemma_rerank, user_query, raw_results, top_k)
        
        top_results = []
        for idx in selected_indices:
            if 0 <= idx < len(raw_results):
                top_results.append(raw_results[idx])
        
        if not top_results:
             top_results = raw_results[:top_k]

        if stream_callback: 
            stream_callback(f"[SEARCH]Đang phân tích chuyên sâu {len(top_results)} nguồn tốt nhất...")
            for r in top_results:
                stream_callback(f"[SEARCH]LINK:{r['meta']['href']}|{r['meta']['title']}")

        # 3. Parallel Crawl & Analyze with aiohttp
        import aiohttp
        
        async def process_item_async(session, item):
            meta = item['meta']
            url = meta['href']
            title = meta['title']
            
            # Crawl Async
            raw_content = await self.parse_url_content(url, session)
            
            if not raw_content or len(raw_content) < 100: 
                return None
                
            # Intelligence Analysis (Sync -> Thread LLM call)
            intel_report = await asyncio.to_thread(self.summarize_with_ai, raw_content, user_query, title)
            
            if intel_report:
                if stream_callback: stream_callback(f"[SEARCH]Đã tóm tắt: {title}")
                return f"{intel_report}\nURL: {url}\n"
            else:
                return None

        # Create Session and Gather
        async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) width aiohttp'}) as session:
            tasks = [process_item_async(session, item) for item in top_results]
            results = await asyncio.gather(*tasks)
        
        final_context = [r for r in results if r]
        
        if not final_context:
            if stream_callback: stream_callback(f"[SEARCH]Không trích xuất được thông tin tin cậy.")
            return "Intelligence Agents reported no reliable information found."
        
        # Sort context by length or quality? Text length is a proxy for detail.
        final_context.sort(key=len, reverse=True)

        if stream_callback: stream_callback(f"[SEARCH]Đã tổng hợp dữ liệu thời gian thực.")
        return "\n".join(final_context)

# Singleton Instance
search_engine = AdvancedSearch()

async def basic_search(query: str, max_results: int = 3):
    return await search_engine.search_and_rerank(query, initial_fetch=15, top_k=max_results)


if __name__ == "__main__":
    # Test
    res = basic_search("tin tức AI mới nhất", max_results=3)
    print(res)


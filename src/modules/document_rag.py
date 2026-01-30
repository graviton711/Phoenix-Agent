"""
Advanced Document RAG System
Hybrid retrieval with semantic search + BM25, contextual chunking, and LLM reranking.
"""
import os
import json
import hashlib
import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import re

# Vector DB
import chromadb

# BM25
from rank_bm25 import BM25Okapi

# Embedding
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Config
EMBEDDING_MODEL = "models/text-embedding-004"
RERANK_MODEL = "llama-4-scout-17b-16e-instruct"  # Lightweight for reranking

# Gemini Keys
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

# =====================================================
# CHUNKING
# =====================================================

def semantic_chunk(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Split text into overlapping chunks, preferring sentence boundaries.
    """
    # Split by sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence_length = len(sentence)
        
        if current_length + sentence_length > chunk_size and current_chunk:
            # Save current chunk
            chunks.append(" ".join(current_chunk))
            
            # Keep overlap
            overlap_text = " ".join(current_chunk)[-overlap:] if overlap > 0 else ""
            current_chunk = [overlap_text] if overlap_text else []
            current_length = len(overlap_text)
        
        current_chunk.append(sentence)
        current_length += sentence_length
    
    # Add last chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return [c.strip() for c in chunks if c.strip()]


def add_contextual_prefix(chunk: str, doc_summary: str, chunk_index: int, total_chunks: int) -> str:
    """
    Add contextual prefix to chunk (Anthropic-style contextual embedding).
    """
    prefix = f"[Document context: {doc_summary[:200]}... | Chunk {chunk_index+1}/{total_chunks}]\n\n"
    return prefix + chunk


# =====================================================
# EMBEDDING
# =====================================================

async def batch_embed(texts: List[str], batch_size: int = 20) -> List[List[float]]:
    """
    Batch embed texts using Gemini API.
    """
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        
        key = key_rotator.get_key()
        if not key:
            raise ValueError("No Google API key configured")
        
        client = genai.Client(api_key=key)
        
        try:
            result = await asyncio.to_thread(
                client.models.embed_content,
                model=EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            all_embeddings.extend([e.values for e in result.embeddings])
        except Exception as e:
            print(f"Batch embed error: {e}")
            # Fallback: empty embeddings
            all_embeddings.extend([[0.0] * 768 for _ in batch])
    
    return all_embeddings


async def embed_query(text: str) -> List[float]:
    """
    Embed a single query.
    """
    key = key_rotator.get_key()
    if not key:
        return [0.0] * 768
    
    client = genai.Client(api_key=key)
    
    try:
        result = await asyncio.to_thread(
            client.models.embed_content,
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"Query embed error: {e}")
        return [0.0] * 768


# =====================================================
# SESSION DOCUMENT STORE
# =====================================================

class SessionDocStore:
    """
    Manages session-scoped document storage with ChromaDB + BM25.
    """
    
    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or os.path.join(os.path.dirname(__file__), "..", "workspace", "doc_index")
        os.makedirs(self.persist_dir, exist_ok=True)
        
        # ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=self.persist_dir)
        
        # Session data: {session_id: {file_hash: {chunks, bm25, collection}}}
        self.session_data: Dict[str, Dict[str, dict]] = {}
    
    def _get_collection_name(self, session_id: str, file_hash: str) -> str:
        """Generate unique collection name."""
        return f"doc_{session_id[:8]}_{file_hash[:8]}"
    
    def is_indexed(self, session_id: str, file_hash: str) -> bool:
        """Check if file is already indexed."""
        return session_id in self.session_data and file_hash in self.session_data[session_id]
    
    def get_indexed_files(self, session_id: str) -> List[str]:
        """Get list of indexed file hashes for session."""
        if session_id not in self.session_data:
            return []
        return list(self.session_data[session_id].keys())
    
    async def index_document(
        self, 
        session_id: str, 
        file_hash: str, 
        file_name: str,
        text: str, 
        summary: str = ""
    ) -> dict:
        """
        Index a document with both vector and BM25.
        Returns indexing stats.
        """
        # Check if already indexed
        if self.is_indexed(session_id, file_hash):
            return {"status": "already_indexed", "file_hash": file_hash}
        
        # Chunking
        chunks = semantic_chunk(text, chunk_size=500, overlap=100)
        
        if not chunks:
            return {"status": "error", "message": "No chunks generated"}
        
        # Add contextual prefix
        if not summary:
            summary = text[:500] + "..." if len(text) > 500 else text
        
        contextualized_chunks = [
            add_contextual_prefix(chunk, summary, i, len(chunks))
            for i, chunk in enumerate(chunks)
        ]
        
        # Batch embed
        embeddings = await batch_embed(contextualized_chunks)
        
        # Create ChromaDB collection
        collection_name = self._get_collection_name(session_id, file_hash)
        collection = self.chroma_client.get_or_create_collection(name=collection_name)
        
        # Add to ChromaDB
        ids = [f"{file_hash}_{i}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=contextualized_chunks,
            metadatas=[{"file_name": file_name, "chunk_index": i} for i in range(len(chunks))]
        )
        
        # Create BM25 index (tokenize on words)
        tokenized_chunks = [chunk.lower().split() for chunk in chunks]
        bm25 = BM25Okapi(tokenized_chunks)
        
        # Store session data
        if session_id not in self.session_data:
            self.session_data[session_id] = {}
        
        self.session_data[session_id][file_hash] = {
            "chunks": chunks,
            "contextualized_chunks": contextualized_chunks,
            "bm25": bm25,
            "collection": collection,
            "file_name": file_name,
            "indexed_at": datetime.now().isoformat()
        }
        
        return {
            "status": "indexed",
            "file_hash": file_hash,
            "file_name": file_name,
            "chunk_count": len(chunks)
        }
    
    def cleanup_session(self, session_id: str):
        """Remove all documents for a session."""
        if session_id not in self.session_data:
            return
        
        for file_hash in list(self.session_data[session_id].keys()):
            collection_name = self._get_collection_name(session_id, file_hash)
            try:
                self.chroma_client.delete_collection(collection_name)
            except:
                pass
        
        del self.session_data[session_id]


# =====================================================
# HYBRID RETRIEVER
# =====================================================

class HybridRetriever:
    """
    Hybrid retrieval with semantic search + BM25 + reranking.
    """
    
    def __init__(self, doc_store: SessionDocStore):
        self.doc_store = doc_store
    
    async def vector_search(self, session_id: str, query: str, top_k: int = 10) -> List[Tuple[str, float, dict]]:
        """
        Semantic search across all indexed documents in session.
        Returns: [(chunk_text, score, metadata), ...]
        """
        if session_id not in self.doc_store.session_data:
            return []
        
        try:
            query_embedding = await embed_query(query)
            
            results = []
            for file_hash, data in self.doc_store.session_data[session_id].items():
                collection = data["collection"]
                
                try:
                    # Run query in thread to avoid blocking event loop
                    search_results = await asyncio.to_thread(
                        collection.query,
                        query_embeddings=[query_embedding],
                        n_results=top_k
                    )
                    
                    if search_results.get("documents"):
                        for i, doc in enumerate(search_results["documents"][0]):
                            distance = search_results["distances"][0][i] if "distances" in search_results else 0
                            score = 1 / (1 + distance)  # Convert distance to score
                            metadata = search_results["metadatas"][0][i] if "metadatas" in search_results else {}
                            results.append((doc, score, metadata))
                except Exception as e:
                    print(f"Vector search skip for {file_hash}: {e}")
                    # Continue to next file even if one fails
                    continue
            
            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        except Exception as e:
            print(f"Vector search critical failure: {e}")
            return []
    
    def bm25_search(self, session_id: str, query: str, top_k: int = 10) -> List[Tuple[str, float, dict]]:
        """
        BM25 keyword search across all indexed documents in session.
        """
        if session_id not in self.doc_store.session_data:
            return []
        
        tokenized_query = query.lower().split()
        
        results = []
        for file_hash, data in self.doc_store.session_data[session_id].items():
            bm25 = data["bm25"]
            chunks = data["contextualized_chunks"]
            file_name = data["file_name"]
            
            scores = bm25.get_scores(tokenized_query)
            
            for i, score in enumerate(scores):
                if score > 0:
                    results.append((chunks[i], score, {"file_name": file_name, "chunk_index": i}))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def reciprocal_rank_fusion(
        self, 
        vector_results: List[Tuple[str, float, dict]], 
        bm25_results: List[Tuple[str, float, dict]],
        k: int = 60
    ) -> List[Tuple[str, float, dict]]:
        """
        Merge results using Reciprocal Rank Fusion.
        RRF Score = sum(1 / (k + rank))
        """
        scores = {}  # chunk_text -> RRF score
        metadata_map = {}
        
        for rank, (text, _, meta) in enumerate(vector_results):
            if text not in scores:
                scores[text] = 0
                metadata_map[text] = meta
            scores[text] += 1 / (k + rank + 1)
        
        for rank, (text, _, meta) in enumerate(bm25_results):
            if text not in scores:
                scores[text] = 0
                metadata_map[text] = meta
            scores[text] += 1 / (k + rank + 1)
        
        # Sort by RRF score
        fused = [(text, score, metadata_map[text]) for text, score in scores.items()]
        fused.sort(key=lambda x: x[1], reverse=True)
        
        return fused
    
    async def retrieve(self, session_id: str, query: str, top_k: int = 5) -> List[str]:
        """
        Full hybrid retrieval pipeline.
        Returns top-k relevant chunks.
        """
        # Parallel search
        vector_results, bm25_results = await asyncio.gather(
            self.vector_search(session_id, query, top_k=10),
            asyncio.to_thread(self.bm25_search, session_id, query, top_k=10)
        )
        
        # Reciprocal Rank Fusion
        fused = self.reciprocal_rank_fusion(vector_results, bm25_results)
        
        # Return top-k chunks (texts only)
        return [text for text, _, _ in fused[:top_k]]


# =====================================================
# GLOBAL INSTANCES
# =====================================================

doc_store = SessionDocStore()
retriever = HybridRetriever(doc_store)


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def get_file_hash(content: bytes) -> str:
    """Generate hash for file content."""
    return hashlib.md5(content).hexdigest()


async def index_uploaded_file(session_id: str, file_hash: str, file_name: str, text: str) -> dict:
    """
    Public API for indexing a file.
    """
    return await doc_store.index_document(session_id, file_hash, file_name, text)


async def retrieve_relevant_chunks(session_id: str, query: str, top_k: int = 5) -> str:
    """
    Public API for retrieving relevant chunks.
    Returns formatted context string.
    """
    try:
        chunks = await retriever.retrieve(session_id, query, top_k=top_k)
        
        if not chunks:
            return ""
        
        context = "\n\n---\n\n".join(chunks)
        return f"[Relevant document/image content]:\n{context}\n\n(Lưu ý: Nếu đây là hình ảnh, nội dung trên chính là mô tả chi tiết của hệ thống thị giác về bức ảnh đó. Bạn hãy dùng nó để trả lời.)"
    except Exception as e:
        print(f"Retrieval error: {e}")
        return ""


def has_indexed_documents(session_id: str) -> bool:
    """Check if session has any indexed documents."""
    return bool(doc_store.get_indexed_files(session_id))


def cleanup_session_documents(session_id: str):
    """Clean up documents when session ends."""
    doc_store.cleanup_session(session_id)

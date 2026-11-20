DB_URL = "postgresql://rag:rag@localhost:5433/rag"

DATA_DIR = "data"
CORPUS_DIR = "corpus"
DOCUMENTS_FILE = "corpus/documents.json"
CHUNKS_FILE = "corpus/chunks.json"
EVAL_DIR = "evaluation"

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

LLM_MODEL = "qwen2.5:3b"  # Mistral était trop lourd pour mon MacBook
LLM_CONTEXT = 8192        # Ollama est à 2048 par défaut

CHUNK_WORDS = 350
MIN_CHUNK_WORDS = 100
OVERLAP_WORDS = 50

TOP_K = 4

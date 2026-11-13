DB_URL = "postgresql://rag:rag@localhost:5433/rag"
DATA_DIR = "data"

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

LLM_MODEL = "qwen2.5:3b"  # assez léger pour tourner sur un portable ; Mistral était trop lourd
LLM_CONTEXT = 4096     # fenêtre de contexte en tokens (Ollama est à 2048 par défaut)

CHUNK_WORDS = 350  # ~500 tokens
OVERLAP_WORDS = 50

TOP_K = 4  # nombre de chunks envoyés au LLM

DB_URL = "postgresql://rag:rag@localhost:5433/rag"
DATA_DIR = "data"

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

LLM_MODEL = "mistral"  # alternatives plus légères : llama3.2:3b, qwen2.5:3b

CHUNK_WORDS = 350  # ~500 tokens
OVERLAP_WORDS = 50

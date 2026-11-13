DB_URL = "postgresql://rag:rag@localhost:5433/rag"

DATA_DIR = "data"                       # PDF bruts (non versionnés)
CORPUS_DIR = "corpus"
DOCUMENTS_FILE = "corpus/documents.json"  # sortie de prepare.py
CHUNKS_FILE = "corpus/chunks.json"        # sortie de chunk.py
EVAL_DIR = "evaluation"

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

LLM_MODEL = "qwen2.5:3b"  # assez léger pour tourner sur un portable ; Mistral était trop lourd
LLM_CONTEXT = 8192        # fenêtre de contexte en tokens (Ollama est à 2048 par défaut)

CHUNK_WORDS = 350      # taille visée pour un chunk (~500 tokens)
MIN_CHUNK_WORDS = 100  # en dessous, le chunk est fusionné avec son voisin
OVERLAP_WORDS = 50  # chevauchement, seulement quand une section trop longue est coupée

TOP_K = 4  # nombre de chunks envoyés au LLM

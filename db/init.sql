CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    doc         TEXT    NOT NULL,
    page        INT     NOT NULL,
    chunk_index INT     NOT NULL,
    content     TEXT    NOT NULL,
    embedding   vector(1024) NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);

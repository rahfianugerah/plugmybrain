-- Runs once on an empty data directory. pgvector ships in the image, but the extension still
-- has to exist inside the target database before cognee can create a vector column.
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant usage to postgres user (already owner, but explicit is good)
GRANT ALL ON SCHEMA public TO postgres;

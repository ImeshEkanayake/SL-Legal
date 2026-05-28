from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RagSettings(BaseSettings):
    """Runtime settings for the RAG services."""

    model_config = SettingsConfigDict(env_prefix="SL_LEGAL_", env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql+psycopg://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
    opensearch_url: str = "http://localhost:9200"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6380/0"
    chunk_index_path: str = "data/indexes/rag_chunks.jsonl"
    opensearch_index: str = "sl_legal_retrieval_chunks"
    qdrant_collection: str = "sl_legal_retrieval_chunks"
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    retrieval_candidate_size: int = 20
    max_pack_items: int = 24
    max_pack_tokens: int = 12000


settings = RagSettings()

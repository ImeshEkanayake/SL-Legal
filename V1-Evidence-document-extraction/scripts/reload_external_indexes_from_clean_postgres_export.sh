#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CHUNKS="data/indexes/rag_chunks_from_postgres_clean.jsonl"
LOG_DIR="logs/index_reload"
mkdir -p "$LOG_DIR"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] reload started"
echo "chunks=$CHUNKS"

if [[ ! -s "$CHUNKS" ]]; then
  echo "missing chunk export: $CHUNKS" >&2
  exit 1
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] chunk_file_rows=$(wc -l < "$CHUNKS")"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] opensearch reload starting"
python3 scripts/load_rag_chunks_opensearch.py \
  --chunks "$CHUNKS" \
  --recreate \
  --batch-size 1000
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] opensearch reload finished"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qdrant reload starting"
PYTHONPATH=rag uv run --with-requirements requirements-rag.txt python scripts/load_rag_chunks_qdrant.py \
  --chunks "$CHUNKS" \
  --provider sentence-transformers \
  --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --dimensions 384 \
  --batch-size 64 \
  --progress-every 5000 \
  --recreate
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qdrant reload finished"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] consistency check starting"
PYTHONPATH=rag uv run --with-requirements requirements-rag.txt python scripts/check_rag_index_consistency.py
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] reload complete"

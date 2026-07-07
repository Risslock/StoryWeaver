# Contract: backfill_lexical_index.py CLI

**File**: `packages/rag/rag/knowledge/backfill_lexical_index.py`
**Purpose**: One-time migration that populates `knowledge_lexical` for chunks ingested before hybrid search existed, from already-stored Chroma metadata/text — no re-embedding, no re-ingestion (FR-011, SC-004, SC-005)

---

## Invocation

```
python -m rag.knowledge.backfill_lexical_index [OPTIONS]
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--campaign-id UUID` | None (all campaigns) | Restrict backfill to one campaign's collection plus the global collection. Omit to backfill every known campaign collection. |
| `--dry-run` | `false` | Report how many chunks would be written per collection without writing anything. |
| `--chroma-path PATH` | `./data/chroma` | Path to the ChromaDB persistent store (matches `ChromaVectorStore`'s default). |

## Behavior

1. Calls `SQLiteLexicalStore.ensure_table()` (idempotent `CREATE VIRTUAL TABLE IF NOT EXISTS`).
2. Always processes `knowledge_global`. If `--campaign-id` is given, also processes `knowledge_{campaign_id}`; otherwise discovers all `knowledge_*` campaign collections that exist in the Chroma path.
3. For each collection: calls `ChromaVectorStore.get_all(collection_name)`, then upserts each `(chunk_id, original_text, metadata)` triple into `SQLiteLexicalStore` in batches (batch size matches `KNOWLEDGE_ENRICH_BATCH_SIZE` for consistency with the rest of the pipeline's batching, though no LLM calls are made here).
4. Logs, per collection, at INFO level: collection name, chunk count found, chunk count written.
5. On completion, prints a summary: total collections processed, total chunks backfilled, elapsed time.
6. Safe to re-run at any time (upsert is idempotent per `chunk_id` — see [lexical-store-interface.md](lexical-store-interface.md)); re-running after new content has been ingested normally is a harmless no-op for already-synced chunks.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Backfill completed (including a no-op re-run) |
| 1 | Chroma path unreadable, `--campaign-id` not a parseable UUID, or an unrecoverable SQLite error |

## Example

```bash
# Backfill every existing collection
python -m rag.knowledge.backfill_lexical_index

# Preview only, one campaign
python -m rag.knowledge.backfill_lexical_index --campaign-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 --dry-run
```

Expected stdout:
```
[INFO] Processing knowledge_global — 342 chunks found
[INFO] Processing knowledge_global — 342 chunks written
[INFO] Processing knowledge_a1b2c3d4e5f67890abcdef1234567890 — 118 chunks found
[INFO] Processing knowledge_a1b2c3d4e5f67890abcdef1234567890 — 118 chunks written
[INFO] Done. 2 collections, 460 chunks backfilled in 3.1s
```

## Relationship to SC-004

This command must be run once before the harness comparison in SC-004 ("no re-ingestion of already-embedded content required") — it is the mechanism that makes that requirement achievable without re-ingesting the gold-standard corpus. It is not itself part of the harness; it is a one-time production/development migration step, documented in [quickstart.md](../quickstart.md).

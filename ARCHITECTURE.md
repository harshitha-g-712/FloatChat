# FloatChat Architecture

## Request path

1. `backend/main.py` validates the API request, loads only well-formed conversation history, and applies a shared per-IP API rate limit.
2. `backend/retrieval/nl_parser.py` attempts validated Gemini structured parsing when configured and falls back to `backend/rule_intent.py`. Every response reports `parser_used` (`llm` or `rules`) and `question_kind` where applicable.
3. Knowledge questions are routed to `backend/rag/indexer.py`; discovery requests use `backend/retrieval/discovery.py`; statistical requests use parameterized SQLite queries in `backend/retrieval/query_engine.py`.
4. `backend/answer_templates.py` generates deterministic summaries. Charts are created by `backend/viz/charts.py`.
5. Authentication/session records live in `AUTH_DB_PATH` (default `backend/floatchat_auth.db`), separate from the read-only/distributable ocean observation database (`DB_PATH`, default `backend/floatchat.db`).

## Data and safety

- Only temperature, salinity, and pressure are available in the bundled measurements table. Unsupported variables are explicitly identified; they must never silently map to temperature.
- SQL values are parameterized and variable columns are allowlisted.
- User conversation operations must verify conversation ownership.
- The bundled ocean database should contain `profiles` and `measurements`, not user accounts, tokens, or chat history.
- Export: results are cached in memory (1 h) and also persisted per chat in `chat_messages.export_data` (`export_store.py`, capped; see README). `/api/export` falls back to the persisted payload, re-running the read-only query if only the intent was stored.
- Questions pass `typo_tolerance.correct_typos` before parsing (original text is what history stores); knowledge answers get a `region_guard.knowledge_region_notice` prefix for uncovered regions.
- Dataset coverage is data-driven: `DATASET_START/END` in `config.py` are read from the first/last profile in the database (reference load: **Bay of Bengal, 1 Jan 2023 – 31 Dec 2024, 37 floats with measurements (38 floats in profiles)**) and user-facing text uses `coverage_label()`. Out-of-region questions are refused and out-of-range dates disclose the real coverage. Seasonal responses must state partial/out-of-range coverage.
- Data cleaning: Database cleanup removed 111 negative-pressure rows (< 0 dbar) and nulled 2 bad surface salinity readings below 20 PSU.

## RAG

FloatChat supports **dual-mode Retrieval-Augmented Generation**:

| Mode | When active | How it works |
|------|-------------|-------------|
| **Embedding** (default) | `GEMINI_API_KEY` is set and `RAG_MODE=embedding` | Documents are embedded with Gemini `text-embedding-004`. Queries are embedded at runtime and matched via cosine similarity. Top results are fed to the LLM for a grounded, cited answer. |
| **TF-IDF** (fallback) | No API key, or `RAG_MODE=tfidf` | Offline scikit-learn TF-IDF vectorizer over the Markdown knowledge base. No network calls. Template-based answer with source labels (`[S1]`, etc.). |

- **Embedding index file:** `backend/rag/embedding_index.json` — rebuild with `python -m rag.build --embeddings`.
- **Knowledge base:** Markdown files in `backend/rag/knowledge/` (ARGO float technology, Bay of Bengal circulation, data quality/QC, and more).
- Retrieval is always filtered to `type=concept` for conceptual answers. Source labels are preserved in both modes.

## Technology Badges (Frontend)

Every chat response includes a `technologies_used` list populated by `_annotate_interpreted()` in `main.py`. The frontend reads this field and renders coloured badge pills at the bottom of each bot message bubble:

- 🤖 **LLM** (green) — GenAI/LLM was used for parsing or answer generation
- 🔍 **NLP** (blue) — always present; intent parsing is applied to every query
- 📚 **RAG** (orange) — retrieval-augmented answer with cited sources
- 📊 **Viz** (purple) — interactive Plotly.js chart was generated

The **Server Status** modal also shows the full technology stack with badge colours.

## Multi-year periods (Round 5)
- `rule_intent._extract_explicit_periods` turns "Month Year" mentions into `compare_periods` (list of `{year, month|None}`) or a cross-year range; `query_engine._retrieve_compare` runs one sub-query per period. Months without a year inherit the next explicit year; a mix of dated and undated months is refused with a clarification.
- Seasons (`retrieval/seasons.py`) are anchored to the year they start in; the north-east monsoon of 2023 is Oct 2023 – Jan 2024. With no year the first dataset year is used and the answer discloses it.

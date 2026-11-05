# ArgoLens — Physics-Informed ARGO Ocean In-Situ Analytics & Conversational Framework

> **IEEE Research Title**: *"ArgoLens: A Physics-Informed Conversational Interface and Geospatial Analytics Framework for Autonomous Ocean Profiling Floats"*

ArgoLens (formerly FloatChat) is a FastAPI + JavaScript scientific platform for querying, analyzing, and visualizing in-situ autonomous ARGO profiling float observations across the Bay of Bengal ($80^\circ\text{E}–95^\circ\text{E}, 5^\circ\text{N}–20^\circ\text{N}$). It integrates deterministic statistical query engines, UNESCO 1983 seawater thermodynamics, WMO Quality Control (QC 1–9) enforcement, interactive geospatial trajectory mapping, and zero-hallucination conceptual retrieval.

## Technologies

FloatChat integrates **four core technologies** that are surfaced as coloured badges on every chat response:

| Badge | Technology | Description |
|-------|-----------|-------------|
| 🤖 **LLM** | GenAI / LLM | Gemini AI for natural-language understanding and answer generation. Auto-enabled when `GEMINI_API_KEY` is set; falls back to deterministic rules without a key. |
| 🔍 **NLP** | Natural Language Processing | Intent parsing via rule-based extractor with typo tolerance; LLM-assisted parsing when Gemini is available. Present on every response. |
| 📚 **RAG** | Retrieval-Augmented Generation | Knowledge questions retrieve relevant documents from the local corpus. Uses **embedding-based retrieval** (Gemini `text-embedding-004`) when a key is present; falls back to **TF-IDF** otherwise. LLM-generated answers are grounded in retrieved sources. |
| 📊 **Viz** | Data Visualization | Interactive Plotly.js charts (depth profiles, maps, distributions, time series, trajectories) rendered in the browser. |

The **Server Status** modal (💡 button in the sidebar) shows which technologies are currently active.

## Requirements

- **Python 3.10 or newer** (developed and tested on Python 3.12.3). `backend/main.py` exits with a clear message on older versions.
- A modern browser. Charts load Plotly from a CDN, so the page needs internet access (or vendor `plotly.min.js` locally).

## Important data limits

- **Data scope:** Bay of Bengal only (the loader's region box is 5–20 N, 80–95 E). The default loader command fetches 1 January 2023 – 31 December 2024 (the end date 2025-01-01 is exclusive). A reference load on 12 Oct 2026 gave **1,441 profile records from 38 floats (37 floats with measurements; 1,373 profiles with measurements, 68 with no measurements in database), 151,555 measurement rows; about 27% of levels have no temperature and no salinity value** (they are excluded from every statistic). Your numbers may differ slightly if Argovis has changed. There is no Arabian Sea or other-ocean data: questions outside the data get an explicit "no data / outside coverage" reply, never an answer built from other data. The covered period in every message is read from the database (`config.coverage_label()`).
- **Data cleaning:** Database cleanup removed 111 negative-pressure rows (< 0 dbar) and nulled 2 bad salinity rows (< 20 PSU, physically impossible surface values in the open Bay of Bengal).
- **Loading data (needs internet):** `python backend/ingestion/fetch_and_load.py --reset` (defaults: 2023-01-01 to 2025-01-01, end exclusive, i.e. through 31 Dec 2024; use `--date-start/--date-end` for another period, `--incremental` to add to an existing database; an `ARGOVIS_API_KEY` raises rate limits), then `python backend/rag/build.py`. `fetch_data.bat` does both. The database file is not shipped in the code ZIP: load it once on your machine. Arabian Sea data would need a different `REGION_BOX` and region support in the parser.
- **Several years:** questions can name a year for each period ("Compare July 2023 and July 2024", "Compare 2023 vs 2024", "between January 2023 and March 2024"). A season without a year ("the south-west monsoon") uses the first dataset year and the answer says so and names the other years. A requested period with no data is listed as "no observations", never dropped.
- **Typos:** a corrected question is answered and shown as `Interpreted as: "..."`; the chat history keeps what the user typed.
- The bundled measurement schema contains **temperature (°C), salinity (PSU), and pressure (dbar)**. It does not contain oxygen, pH, or density measurements; unsupported variables are reported rather than silently replaced with temperature.
- Unqualified temperature **and salinity** averages use the upper 50 dbar and every answer states the depth used. Ask for the full water column explicitly to request all recorded depths.
- **RAG Architecture & Active Retrieval Verification:** FloatChat implements a dual-mode Retrieval-Augmented Generation pipeline:
  - **Offline Active Mode (TF-IDF):** Active whenever running without a live Gemini key or when `RAG_MODE=tfidf`. It uses a scikit-learn TF-IDF vectorizer over the Markdown knowledge corpus (`backend/rag/knowledge/`) with zero network latency, zero API costs, and structured source provenance (`[S1]`, `[S2]`).
  - **Online Augmented Mode (Embedding + LLM Generation):** When `GEMINI_API_KEY` is present and `RAG_MODE=embedding`, queries and corpus sections use Gemini `text-embedding-004` cosine similarity matching, with answers synthesized directly by Gemini and grounded in retrieved passages.
  - **Live Mode Verification:** The currently active mode is reported directly by `GET /api/health` (`rag_mode`), in every chat response object (`rag_mode`), and in the UI's **Server Status** (💡) modal. Rebuild the index at any time with `python scripts/rebuild_rag.py` (or `rebuild_rag.bat`).
- Gemini interpretation is optional. Without a key, validated rules-based parsing is used. Live Gemini and Argovis ingestion require network access and valid credentials.
- **Quality Control (QC) Flags Stored and Applied:** Measurements now store Argo QC flags (`temp_qc` and `sal_qc`). By default, scientific filtering (`good_only`) restricts queries and physical profile calculations to trusted observation flags (QC 1 = Good, 2 = Probably Good, 5 = Adjusted, 8 = Interpolated), strictly nulling out or excluding bad/questionable data (QC 3 = Questionable, 4 = Bad, 9 = Missing) for publishable research standard integrity.

## Architecture

- `backend/main.py` — FastAPI routes, parser orchestration, auth-aware conversation handling.
- `backend/retrieval/nl_parser.py` — validated LLM parser with rules fallback and `parser_used` metadata.
- `backend/rule_intent.py` — deterministic intent extraction and follow-up handling.
- `backend/retrieval/query_engine.py` — parameterized SQL and statistics.
- `backend/retrieval/discovery.py` — coverage, float lists, trajectories, similar profiles.
- `backend/rag/` — local knowledge corpus, dual-mode retrieval (TF-IDF + Gemini embeddings), and RAG answer generation.
- `backend/gemini_service.py` — Gemini client wrapper: LLM parsing, embedding helpers, RAG answer generation.
- `backend/auth.py` — password hashing, token validation, private conversation store.
- `frontend/` — chat UI, technology badges, and Plotly.js charts.
- `tests/` — parser, routing, RAG, regression, technology badges, and API tests.

## Windows quick start

1. Extract the ZIP.
2. Copy `.env.example` to `.env` and edit settings as needed.
3. Run `run_floatchat.bat`, or use PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python backend\main.py
```

Open `http://127.0.0.1:8000`. Do not open `frontend/index.html` directly; the API and frontend are intended to run from the FastAPI server.

## Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python backend/main.py
```

## Configuration

Copy `.env.example` to `.env`. Keep secrets private. `GEMINI_API_KEY` is read server-side and must never be added to frontend files. `DB_PATH` points to the ocean observations database; `AUTH_DB_PATH` points to the separate private account/conversation database. `.env.example` sets `backend/floatchat_auth.db`; if the variable is not set at all the code falls back to `floatchat_auth.db` in the project root. Do not distribute the auth database.

## Tests and evaluation

From the project root:

```bash
python -m pytest -q
python scripts/evaluate.py
```

Tests are offline and do not prove live Gemini/Argovis integration or browser rendering. See `ARCHITECTURE.md`, `EVALUATION_REPORT.md` and `AUDIT_FIXES.md` for system boundaries and change history.

**The tests need the ocean database.** It is not in the code ZIP, so load it first (`python backend/ingestion/fetch_and_load.py --reset`) or point `DB_PATH` at an existing `floatchat.db`. Without it pytest stops immediately with instructions instead of failing hundreds of tests. (`FLOATCHAT_TESTS_NO_DB=1` runs anyway; only the database-free tests then pass.)

## Security and packaging

- **Build the distributable with `python scripts/package.py`.** It excludes `.env*` (except `.env.example`), every `*.db`, logs and caches, and refuses to finish if any of those slip in. Do not zip the project folder by hand.
- Distributables must NOT bundle `backend/floatchat_auth.db` (which contains private user accounts and tokens) or `floatchat.db`.
- User/session/conversation data is stored separately in `AUTH_DB_PATH` (default: `backend/floatchat_auth.db`), which is initialized automatically on startup.
- Ocean observation data in `backend/floatchat.db` can be ingested using `python backend/ingestion/fetch_and_load.py --reset` (or `fetch_data.bat`).
- Do not commit or package `.env`, auth databases, ocean databases (`*.db`), logs, or credentials.
- API requests are rate-limited (120/min per IP, in memory, per process); request bodies over 256 KB and `history` over 50 entries are rejected; conversation access is owner-checked; SQL values are parameterized.
- Responses carry `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a Content-Security-Policy in **report-only** mode (open the browser console, confirm there are no violations, then set `FLOATCHAT_CSP=enforce`). API docs are off unless `ENABLE_DOCS=true`. Plotly is still loaded from its CDN without a Subresource Integrity hash; vendor `plotly.min.js` if you need to remove that dependency.
- If an API key was ever stored in a shared copy of `.env`, rotate it.

## Persistent conversation history

Signed-in users can reopen, search, and delete saved conversations. History is stored separately from ocean observations in `AUTH_DB_PATH` (default: `backend/floatchat_auth.db`), which is created automatically on startup and intentionally is not included in the distributable ZIP. Anonymous chat context is temporary and is not persistent history.

## Round 7 changes

- **No conversation limit:** the history list, export and reset work for any number of saved conversations (ownership is a direct database lookup, not a scan of the newest 100). `GET /api/conversations` and `/search` take an optional `limit` for paging only; there is no maximum.
- **Export cache is per owner:** cached export rows are keyed by user (`u<id>:<conversation>` / `g:<conversation>`), expire after 1 hour, are purged on every save, are capped at 200 entries, and are dropped when a chat is deleted or reset.
- **Usernames:** letters, numbers, hyphens and underscores only; the error message now matches the rule (spaces and dots are rejected). Existing accounts are unaffected: sign-in uses the email.
- **Registration no longer reveals whether an email exists:** a new and an already-registered email get the identical response, so registering does **not** sign you in; the page sends you to the sign-in form. (A taken *username* is still reported, because usernames are not secret.)
- **Download chart image:** every chat chart has a "Download image" button (PNG, 2x resolution), also for charts restored from history.
- **Share a chat:** the share button in the top bar creates a read-only link (`/?share=<token>`) that anyone can open without signing in. The link shows a snapshot as of sharing (use "Update with latest messages" to refresh) and never shows your name or email. "Stop sharing" or deleting the chat kills the link. Guest (not signed-in) chats cannot be shared because they are not saved.

## CSV export, typos and out-of-coverage questions
- **CSV export:** `POST /api/export` uses the in-memory result (kept 1 hour). If that is gone (old chat, server restart), signed-in users still get the CSV: each saved assistant message stores a compact export payload in the history database (never sent to the browser). Results up to 400 KB / 5,000 rows are stored whole; larger ones store only the validated query and the CSV is rebuilt from the ocean database. Only the newest payload per conversation is kept. Chats saved before this feature, and anonymous (not signed-in) chats after a restart, still return 409 "Ask the question again".
- **Typos:** a conservative step (`backend/typo_tolerance.py`) fixes misspellings of a fixed vocabulary (average, temperature, salinity, pressure, maximum, minimum, compare, profile, float, trajectory, month names of 6+ letters, region words) with difflib at cutoff 0.8. It never changes numbers, float IDs or profile IDs, and leaves 5-letter words (e.g. "march", "match") alone.
- **Knowledge questions naming an uncovered region** (e.g. Arabian Sea) begin with a note that only the Bay of Bengal is covered, followed by the Bay of Bengal information. Data questions about uncovered regions are refused.

## Sonar & Dive simulator (dive profile)

`GET /api/floats/{platform}/dive-profile` returns the float's most recent profile **that has measurements** and derives:

- **Sound speed** with Mackenzie (1981); depth in metres is computed from pressure (Saunders 1981, using the profile latitude).
- **Mixed layer depth**: first level 0.2 °C colder than the ~10 dbar value (interpolated). It is temperature-only; in the Bay of Bengal salinity stratification is strong, so a density-based MLD can differ. Returns `null` with `mixed_layer_note` if no level near the surface exists or no drop occurs.
- **Thermocline**: strongest |dT/dp| over at least 5 dbar, searched in the upper 500 dbar only.
- **SOFAR axis**: minimum of the smoothed sound speed between 300 and 2000 dbar. Only reported if the profile reaches 1000 dbar and the minimum is not at the window edge; `sofar_band` gives the depth range within 0.5 m/s of the minimum because the minimum is broad and flat. Otherwise `null` with `sofar_note`.

All depth values in the response and the UI are in dbar. These are screening-level estimates for exploration, not validated acoustic products.

## Review fixes (Oct 2026)

- Dive profile: newest profile with data is used (2 floats used to 404), Mackenzie sound speed, bounded thermocline, honest SOFAR/MLD "not resolved" handling.
- Follow-up questions: filters carried over from the previous question are now stated in the reply (`context_note`); stand-alone "how many floats/profiles" questions and unrecognisable text no longer inherit them.
- "Which floats are deepest/shallowest" now sorts by mean maximum depth.
- Request limits, security headers, docs off by default, health endpoint no longer reports the model name, rate-limiter sweep every 30 s.
- PBKDF2 fallback uses 600,000 iterations (existing hashes still verify); Argon2 remains the default.
- Tests stop early with instructions when the ocean database is missing; packaging refuses archives containing secrets or databases.

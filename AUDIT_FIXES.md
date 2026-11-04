# FloatChat audit fixes

## Round 7

- **Python version:** `main.py` contained an f-string that reused double quotes inside `{}` (only valid on Python 3.12+), while the docs and `.bat` claimed 3.10+. It is now a plain helper function (`_intent_cache_key`), `main.py` checks `sys.version_info >= (3, 10)` at startup, and README / `.bat` / `.sh` state "3.10+, tested on 3.12.3".
- **Export-cache leak:** the in-memory cache was keyed by the client-supplied conversation id alone, so a guest could send a signed-in user's id and read or overwrite that user's cached rows; entries also outlived chat deletion and expired entries were never purged. Keys are now per owner, purged on save, hard-capped, and cleared on delete/reset.
- **100-conversation limit:** export and reset checked ownership by scanning `get_conversations()` (default 100). They now use `conversation_owned()`; the list/search endpoints have no maximum (`limit` is optional).
- **Username message vs regex** and **email enumeration on register:** see README "Round 7 changes".
- **New features:** chart PNG download, read-only share links (`/api/conversations/{id}/share`, `/api/shared/{token}`).
- **Small extra:** the registration form said "min 8" characters while the server requires 10; the form now says and enforces 10.
- **Verification:** `tests/test_round7.py` added; existing tests updated for no-auto-login on register. In the authoring sandbox FastAPI, pydantic and argon2 were not installable (no network), so only the storage-layer tests and the cache helpers were executed there; the HTTP-level tests and the browser UI were **not** run. Run `python -m pytest -q` on your machine.

This package contains targeted fixes based on end-to-end checks of the supplied ZIP.

## Fixed

- A single explicit pressure level such as `at 2000 dbar` is now parsed as an exact inclusive pressure filter rather than ignored.
- Float/profile count questions reuse the same validated SQL filters as data queries, including date, pressure, platform, and region filters.
- Knowledge retrieval now returns a ranked Markdown section rather than the entire first matching knowledge document, reducing generic and irrelevant answers.
- Responses for validation, unsupported-variable, ambiguous, and no-data early-exit paths are persisted to the user's conversation history as well as normal responses.
- Responses to requests extending beyond the available years disclose the actual bundled dataset coverage.

## Conversation history

- History is stored persistently in the separate SQLite database configured by `AUTH_DB_PATH` (default: `backend/floatchat_auth.db`).
- Signed-in users can list, search, reopen, and delete their own conversations.
- User ownership is checked before loading or deleting conversation messages.
- The private authentication/history database is intentionally not bundled in this ZIP; it is initialized automatically at startup. Users must sign in for persistent cross-session history.
- Anonymous multi-turn context is temporary in memory and is not persistent history.

## Verification run

- `python -m compileall -q backend tests` — passed.
- `python -m pytest -q` — 79 tests passed, 39 subtests passed.
- `python scripts/evaluate.py` — 4/4 smoke cases passed.
- `node --check frontend/script.js` — passed.
- ZIP integrity check — passed.

Gemini and live Argovis calls were not verified because no API key was configured. The bundled ocean data remains January–June 2023; no additional years were fabricated or added.

## History sidebar fixes (2026-10-11)

Frontend (`frontend/script.js`, `frontend/style.css`)
- Logout / session loss / login now wipe messages, sidebar list, search box and conversation id (`resetUiState`), so one user's chats never show for the next user of the same browser.
- Reopening a chat fetches first and only then replaces the view; failures show a message instead of a blank screen. 401/403 on any history call returns to sign-in.
- Out-of-order responses are ignored (request counters); an answer that arrives after switching chats is no longer painted into the wrong chat; switching chats while a reply is loading is refused with a message.
- Refreshing the page restores the current conversation instead of showing an empty chat tied to an old id.
- Delete asks for confirmation; rows are now a `<div>` with two sibling buttons (open / delete) with `aria-current` on the active chat.
- Delete button is visible on touch devices and on keyboard focus.
- History list height is `40vh` (was fixed 220px) and no longer collapses when the sidebar overflows (`flex-shrink: 0`).

Backend (`backend/auth.py`, `backend/main.py`)
- Saved assistant messages keep `chart_data` (dropped only above 300,000 characters) so reopened chats redraw their charts; the early-exit path uses the same payload builder.
- Search escapes `%`, `_` and `\`, searches via `EXISTS` (no duplicate rows), returns `message_count`, and a blank query returns the normal list.
- Titles are always truncated to 60 characters.
- Conversation ids must match `^[A-Za-z0-9_-]{1,64}$` (UUIDs fine): 422 on `/api/chat`, 404 on history routes.
- Messages are ordered by `created_at, id`.

Tests: `tests/test_history.py` (storage layer + API round trip, isolation between users, id validation, search escaping).
Not covered by the bundled tests: browser behaviour. It was verified separately with a headless Chromium run against a mock API (18/18 checks).

## History sidebar round 2 (2026-10-11)

Frontend (`frontend/script.js`, `frontend/style.css`)
- A network error or non-401/403 response on `/api/me` no longer deletes the saved token and logs the user out; the app shows "Retrying in 5 seconds" and recovers automatically. Only 401/403 ends the session.
- "New chat" now cancels any chat still loading, so a slow request can no longer paint an old chat over the new one.
- CSV export shows the server's message (e.g. "Ask the question again") instead of a generic "Export failed."; 401/403 returns to sign-in.
- The sidebar loads 100 chats and offers a "Load more" button (+100 each time) for both the list and search.

Backend (`backend/auth.py`, `backend/main.py`)
- `/api/chat` is crash-safe: if the pipeline raises, the question and an error reply are both saved, so a reopened chat never shows a question with no answer. The client gets a generic 500 message with no internals.
- `/api/export` returns 409 with a clear message when the chat's results are no longer cached (server restart / over 1 hour) instead of an empty CSV. Results are still cached in memory only.
- `GET /api/conversations` and `/api/conversations/search` accept `limit` (1-500, default 100). Search and list now use the same default.
- All auth/history SQLite connections go through `_connect()`: 10 s busy timeout, WAL journal and enforced foreign keys (so `ON DELETE CASCADE` really works). `.gitignore` now covers `*.db-wal`, `*.db-shm`, `*.db-journal`.

Verification
- `python -m pytest -q`: 103 passed (7 new tests in `tests/test_history.py`).
- `node --check frontend/script.js`: passed.
- Headless Chromium against the real backend (`tests/ui_history_check.py`): 10/10 checks (network error, 500 and 401 on `/api/me`, auto-recovery, New-chat-vs-slow-load race, Load more paging, export 409 message). Sandbox had no internet, so Google Fonts/CDN requests failed; nothing depended on them.
- Not verified: live Gemini/Argovis, and other browsers (Firefox/Safari).
Known limit: export results are still in memory only; rebuilding them for old chats would need the rows stored with each message.

## Question & answer fixes (round 3, 2026-10-11)

Found by running ~40 questions through `/api/chat` and checking each number against the raw SQLite data.

- **Empty concept answers:** "What is the thermocline / halocline / pycnocline?" returned only the document title. The heading-only `# Title` block outranked the real sections. Empty sections are now skipped (`rag/indexer.py`).
- **Regions the data does not cover** (Arabian Sea, Pacific, Mediterranean, ...) were answered with Bay of Bengal data. They are now refused with an explanation. Knowledge questions that merely mention another sea are not blocked.
- **Sub-regions were applied but never reported:** "north Bay of Bengal", "Andaman Sea" etc. filtered the data while the answer said "in the Bay of Bengal". `named_region` is now returned in the filters and named in the answer.
- **"winter / summer / spring / autumn" were silently ignored** (the whole year was averaged). The bot now asks for months or a monsoon period.
- **"at 2000 dbar" returned no data** because no level is sampled at exactly 2000.0. A single level now uses a +/-10 dbar band, and the answer states the band (1990-2010 dbar).
- **Inconsistent default depth:** temperature averages used the upper 50 dbar but salinity averages used the whole water column (April: 34.64 vs 33.25 PSU). Both now default to the upper 50 dbar, and every answer states its depth ("shallower than 50 dbar" / "at all depths"). "at all depths" in the question still overrides it. Comparison answers state the depth too.
- **"warmest / coldest / saltiest / freshest month"** returned a single maximum value instead of a month. It now ranks the months and lists the monthly means.
- **Unknown float / profile IDs** gave "no temperature observations". They now say the ID is not in the dataset and suggest real ones.
- **Float profile answers** now name the float and no longer read "Across ... across ...".
- **Coverage** says "Profiles with measurements: 226 (244 profile records in the database; 18 have no measurement rows)" so it agrees with `/api/health`.
- **Greetings** ("hello", "good morning") get a friendly reply instead of an off-topic refusal.

Tests: `tests/test_qa_fixes.py` (28 tests, several compare answers with direct SQL). Full suite: 131 passed.

Known limits (not changed): misspelled questions ("avarage temprature") fall back to an all-depth summary; the knowledge base only covers the Bay of Bengal, so "Arabian Sea vs Bay of Bengal" concept questions get a Bay of Bengal answer; results of open-ended "trend" questions are summarised in text and shown as a chart.

## Round 4 (2026-10-11)

Sandbox limits: no internet, and FastAPI/pytest/uvicorn/pydantic were not installable, so the web API, the 131 existing tests, `evaluate.py` and all browser/Gemini checks were NOT run. Logic that does not need FastAPI was run under throwaway pytest/pydantic shims (not shipped).

- **CSV export for reopened chats** (`export_store.py`, `auth.py`, `main.py`): new `chat_messages.export_data` column (auto-migrated), never returned to the browser. Whole result stored up to 400 KB / 5,000 rows, otherwise the validated intent only and the CSV is rebuilt from the database. Only the newest payload per conversation is kept. Old chats without a payload still give the clear 409. `tests/test_export_persistence.py` (10 tests, run). `test_history.py`'s old 409 test was rewritten (cache cleared -> same CSV; legacy chat -> 409) and was **not run**.
- **Typo tolerance** (`typo_tolerance.py`, wired in `main.py` after the user message is saved): 6+ letter standalone words only, difflib cutoff 0.8, same first letter, known-word protection list. Scanning the existing tests' questions exposed false positives (match->march, fresher->freshest, freshen, monsoons); all fixed and covered. `tests/test_typo_tolerance.py` (5 tests incl. 20 misspellings, run). Limitation: 5-letter typos are not fixed.
- **Coverage is data-driven** (`config.py`): `DATASET_START/END` come from the profiles table; `coverage_label()` replaces hard-coded "January–June 2023" in `main.py`, `rule_intent.py`, `answer_templates.py`. Output is unchanged for the bundled data. UI no longer says "LIVE" or hard-codes dates.
- **Knowledge gaps** (`region_guard.py`): knowledge answers naming an uncovered region start with a note that only the Bay of Bengal is covered. No new knowledge notes were added (nothing could be verified here). `tests/test_region_guard.py` (run); the API-level test in `test_qa_fixes.py` was updated, **not run**.
- **Not done:** loading 2+ years (no internet), `tests/ui_full_check.py` and cross-browser runs, Gemini tests (no key), full pytest/evaluate.
- **Number check (offline, not via /api/chat):** 17 new questions through parser -> `retrieve()` -> `build_answer()` all matched direct SQL.

### Round 4b – chart review (code read only; charts were NOT rendered)
plotly was not installable here, so `viz/charts.py` could not be executed. Found by reading it and fixed in `backend/viz/charts.py`:
- Compare chart: overlaid histograms were fully opaque (one period hid the other) -> `opacity=0.6`.
- Depth profile silently drew only the first 15 profiles -> title now says "showing 15 of N profiles".
- Timeseries, distribution and compare charts did not state which depths they mix (an all-depth mean looks like a surface value) -> title now shows the plotted pressure range, e.g. "| 0–50 dbar"; timeseries is labelled "daily mean".
- Checked and fine: depth axis is reversed with units on both axes; the pandas daily aggregation works on pandas 3.0.
- New `tests/test_chart_quality.py` (4 tests) – skipped here (no plotly); run it on your machine. Not yet done: browser rendering/screenshots and a visual review of map and trajectory charts.

## Round 5 (2026-10-11) – verified against the real API

Run in a sandbox WITH FastAPI/pytest/plotly but WITHOUT access to Argovis, Gemini or a browser.

- Fixed the one failing Round-4 test (compare-chart opacity lives in `marker.opacity`; test was wrong).
- 20 new questions asked through `/api/chat`; every number checked against direct SQL on `backend/floatchat.db`.
- Bugs found and fixed (tests in `tests/test_round5.py`): short month typos before a year ("Aprl 2023") silently dropped the month; "profile for March 2023" was treated as an invalid float ID; "depth profiles" (plural) gave no depth chart; "What is the data coverage?" was refused; "trajectory of the first float" said "float None".
- Depth wording: "shallower than 50 dbar" -> "up to 50 dbar" (the SQL bound is inclusive).
- Depth-profile chart picks 15 profiles spread across floats and dates (`_pick_spread_profiles`), deterministic.
- Typo step now adds `Interpreted as: "..."` to the answer and an `interpreted_as` response field; history keeps the original text.
- Anonymous export: clear 404/409 messages that suggest signing in (guest data is not persisted).
- `tests/conftest.py` keeps test accounts out of the real auth DB. Unused `csv`/`io` imports removed from `main.py`.
- Result: 187 tests pass; `scripts/evaluate.py` passes.

NOT done (needs your machine): loading 2+ years of data (Argovis unreachable), browser verification (`tests/ui_full_check.py`), Gemini tests (no key), season logic / docs review for new years.

### Round 5b – multi-year data (2023-01-01 to 2024-12-31 loaded on the maintainer's machine)
Maintainer's pytest on the real 2-year DB: 183 passed, 4 failed (all `test_seasons_routing`, which hard-coded the Jan–Jun 2023 window). Fixed by pinning the window in those tests; code was correct.
A synthetic 2-year database (`tests/test_new_years.py`, numbers checked against SQL) then exposed real bugs, fixed:
- "Compare salinity between July 2023 and July 2024" answered July 2023 only (second period silently dropped). New `compare_periods`; also "Compare 2023 vs 2024" and "between January 2023 and March 2024" (range no longer cut to the first month).
- Date wording said "between October and January 2023" for the north-east monsoon; now "between October 2023 and January 2024".
- A season asked without a year silently used 2023; the answer now says so and names the other years.
- A comparison period with no data (e.g. March 2025) was omitted; it is now listed as "no observations".
- Loader default end date changed from 2023-06-30 to 2025-01-01 so `fetch_data.bat` loads two years.
Result: 208 tests pass in the sandbox (on the Jan–Jun 2023 DB plus the synthetic 2-year DB). NOT run against the real 2-year DB by me: the DB was never uploaded, so the numbers in the maintainer's DB were not verified against SQL by me.

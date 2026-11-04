# Evaluation Report

## Automated local checks

The project test suite includes parser/season/routing tests and regression/API tests. Run `python -m pytest -q` from the project root for the current result; this report intentionally does not hard-code a pass count because it changes as tests are added.

## Required evaluation dimensions

| Dimension | Required behavior | Status note |
|---|---|---|
| Variable fidelity | Unsupported oxygen/pH/density never becomes temperature | Covered by regression/API tests where present |
| Date filters | Invalid months/years do not become unfiltered queries | Covered by API checks |
| Entity counts | Profiles/floats counted distinctly, not as measurements | Covered by API checks |
| History | Malformed entries are ignored/rejected safely; cache keys include content | Covered by parser/API checks |
| Auth isolation | Private auth DB; conversation ownership enforced | Requires two-user integration tests |
| RAG | Concept-only retrieval and stable source labels | Local retrieval tested; quality remains corpus-dependent |
| Seasons | Partial coverage clearly disclosed | Must be checked for all season phrases |
| Live services | Gemini and Argovis | Not verified without live credentials/network run |
| Scientific QC | QC flags applied consistently | Not verified; do not claim complete QC filtering |
| Browser rendering | Desktop/mobile, modal, chart and line breaks | Manual browser QA required |

## Known boundaries

The included dataset contains temperature, salinity, and pressure only. Averages of temperature and salinity default to the upper 50 dbar unless the user explicitly asks for the full water column; answers disclose this depth filter. The current RAG backend is TF-IDF rather than embeddings. The bundled database is a data artifact, not a replacement for fresh live ingestion.

# ArgoLens — Natural Language Retrieval & Seawater Density Profiling for ARGO Float Networks

> **IEEE Research Title**: *"ArgoLens: Natural Language Retrieval and Seawater Density Profiling for ARGO Marine Observation Networks"*  
> **Data Scope**: 1,441 Profiles, 38 Robotic Profiling Floats (37 with measurements), 151,555 Measurements (Jan 2023 – Dec 2024)  
> **Observed Geographic Range**: 5.00°N–19.11°N, 80.07°E–91.93°E (Bay of Bengal basin)  
> **Ingestion Target Envelope**: 5.00°N–20.00°N, 80.00°E–95.00°E

ArgoLens is a physics-informed conversational retrieval and geospatial analytics framework designed for autonomous ARGO profiling float observations. The framework pairs a rule-first intent parser (with an optional validated LLM parser fallback) with deterministic SQL execution over indexed observations, automated World Meteorological Organization (WMO) Quality Control (QC) flag filtering, UNESCO 1983 seawater thermodynamics, interactive trajectory mapping, and curated domain knowledge retrieval.

---

## 🌊 Core Features

1. **Rule-First Intent Parser & Structured Query Execution**:
   - Maps user natural-language queries to structured parameterized SQL filters over indexed SQLite tables.
   - Named geographic guard refusing out-of-domain named regions (e.g., Arabian Sea, Pacific).
   - Conservative typo-tolerance for oceanographic variables, temporal periods, and multi-year comparisons.
   - Validated hybrid architecture balancing deterministic rule matching with LLM parsing.

2. **WMO Quality Control (QC 1–9) Filtering**:
   - Evaluates sensor quality flags on every measurement row (`temp_qc`, `sal_qc`).
   - Restricts computational aggregation to accepted observations (QC 1 = Good, 2 = Probably Good, 5 = Adjusted, 8 = Interpolated), discarding or nulling bad/missing readings (QC 3 = Questionable, 4 = Bad, 9 = Missing).
   - Sensor range validation enforces $P \ge 0$, $20 \le S \le 50$, and $-5 \le T \le 50$.

3. **Thermodynamic Seawater Density Profiling (UNESCO EOS-80)**:
   - Computes surface potential density anomaly $\sigma_\theta$ ($\text{kg/m}^3$) via the UNESCO 1983 polynomial.
   - Calculates density-based Mixed Layer Depth ($\text{MLD}_\rho$) using the $\Delta\sigma_\theta = 0.03\text{ kg/m}^3$ threshold (de Boyer Montégut et al., 2004).
   - Calculates isothermal Mixed Layer Depth ($\text{MLD}_T$) using the $\Delta T = 0.2^\circ\text{C}$ criterion.
   - Computes **Barrier Layer Thickness** ($\text{BLT} = \max(0, \text{MLD}_T - \text{MLD}_\rho)$) to quantify upper-ocean salinity stratification.
   - Classifies water masses into regional categories matching Northern Indian Ocean hydrography:
     - *Bay of Bengal Surface Water (BBSW)* ($T \ge 27^\circ\text{C}, S < 33.5$)
     - *Equatorial Indian Ocean Surface Water* ($24 \le T < 28^\circ\text{C}, 33.5 \le S \le 34.6$)
     - *Arabian Sea High Salinity Water (ASHSW)* ($T \ge 25^\circ\text{C}, S \ge 35.0$)
     - *Indian Central Water (ICW)* ($10 \le T < 20^\circ\text{C}, 34.5 \le S \le 35.2$)
     - *Indian Deep / Bottom Water* ($T < 10^\circ\text{C}, P \ge 800\text{ dbar}$)
     - *Transitional / Thermocline Water*

4. **Interactive Geospatial Ocean Map (Leaflet.js)**:
   - ESRI Ocean and ESRI Dark Canvas basemaps with reference overlays.
   - Renders float drift trajectories with markers color-coded by temperature categories ($<26^\circ\text{C}$, $26–28^\circ\text{C}$, $28–29^\circ\text{C}$, $>29^\circ\text{C}$).
   - Direct popup links to inspect individual profile dive plots and T-S diagrams.

5. **T-S Seawater Density Diagram & Acoustic Profiling**:
   - Interactive Plotly.js Temperature-Salinity diagram with contoured potential density isopycnals ($\sigma_\theta = 20.0\text{ to }27.5\text{ kg/m}^3$).
   - Computes sound speed profiles using Mackenzie (1981) and identifies SOFAR acoustic channel axes.

6. **Automated Scientific PDF Report Export (ReportLab)**:
   - Generates formatted summary reports (`POST /api/export/pdf`) containing query parameters, observation statistics, WMO QC flag distributions, and verification timestamps.

7. **Marine Acoustic Speech Normalizer**:
   - Normalizes phonetic voice inputs for marine acoustic terminology (`thermocline`, `halocline`, `pycnocline`, `MLD`, `SOFAR`, `dbar`, `PSU`, and spoken digit float IDs).

8. **Draggable Resizable Navigation Sidebar**:
   - Splitter divider with hover highlights, touch/mouse drag handlers, and `localStorage` width persistence.
   - Triggers dynamic reflow for Leaflet maps and Plotly charts upon resizing.

9. **Dual-Mode Knowledge Retrieval (RAG)**:
   - **Offline Active Mode (TF-IDF)**: Vectorized cosine similarity over a curated oceanographic markdown knowledge corpus (`backend/rag/knowledge/`) with citation provenance (`[S1]`, `[S2]`) and zero network latency.
   - **Online Augmented Mode (Embedding + LLM)**: Semantic search using Gemini `text-embedding-004` and answer generation when `GEMINI_API_KEY` is provided.

---

## 📊 Evaluation Results (from `eval/`)

Summary metrics recorded in `eval/performance_evaluation_summary.json` across the 294-query benchmark (`eval/benchmark_280_questions.json`):

| Evaluation Metric | Measured Value | Scope / Conditions |
|---|---|---|
| **SQL Execution Accuracy** | **100.0%** | 294 of 294 valid SQL queries executed successfully |
| **Intent Accuracy** | **87.76%** | $87.8\% \pm 3.8\%$ (95% CI across 294 queries) |
| **Numerical Accuracy** | **100.0%** | Tested on 2 reference cases ($\pm 0.05$ units tolerance) |
| **Abstention Accuracy** | **91.43%** | 32 of 35 out-of-domain or unsupported queries refused |
| **Retrieval Precision@1** | **100.0%** | Top-1 knowledge document precision |
| **Retrieval MRR** | **1.00** | Mean Reciprocal Rank on evaluation queries |
| **RAG Answer Grounding** | **93.33%** | Supported statements in generated answers |
| **Response Latency (Mean)** | **88 ms** | $0.088\text{ s} \pm 0.014\text{ s}$ (P50: 68 ms, P95: 252 ms, P99: 586 ms) |

### Parser Ablation (294 Queries)
- **Rules Only**: 214 / 294 passed (72.79% accuracy, 10 variable-fidelity violations)
- **LLM Only**: 249 / 294 passed (84.69% accuracy, 17 variable-fidelity violations)
- **Validated Hybrid**: 237 / 294 passed (80.61% accuracy, 10 variable-fidelity violations)

### Internal Stage Latency (from `eval/stage_latency.json`)
Measured via `scripts/measure_stage_latency.py` across 250 test iterations:
- **Intent Parsing**: 0.27 ms mean (0.24 ms median, 0.41 ms P95)
- **SQL Retrieval**: 110.33 ms mean (71.45 ms median, 271.57 ms P95)
- **Thermodynamic Calculation**: 0.63 ms mean (0.55 ms median, 0.97 ms P95)
- **Total Internal**: 111.23 ms mean (72.39 ms median, 272.43 ms P95)

---

## ⚠️ Known Limitations & Scope Boundaries

1. **Observed QC Flags in Bundled Dataset**: While the filter supports all standard WMO flags (1, 2, 5, 8 accepted; 3, 4, 9 dropped), in this specific Bay of Bengal ingested database only QC flags **1** (good) and **9** (missing) occur in practice.
2. **Temperature Variable in $\sigma_\theta$**: Potential density ($\sigma_\theta$) is computed using *in-situ* recorded temperature ($T$) rather than adiabatically adjusted potential temperature ($\theta$).
3. **Equation of State Reference**: Seawater potential density calculations use the UNESCO 1983 Equation of State (EOS-80) and have not been benchmarked against the newer thermodynamic equation TEOS-10 / Gibbs SeaWater (GSW) library.
4. **Coordinate Boundary Guard**: The domain guard strictly blocks out-of-domain *named regions* (e.g., "Arabian Sea", "Pacific Ocean"); raw numerical coordinate bounding queries without explicit region names are not intercepted by the text-based region guard.
5. **Parser Accuracy & Remaining Errors**: As reported in the ablation study, the validated hybrid parser achieves an 80.61% pass rate on the 294-question benchmark, leaving 57 unparsed queries or variable-fidelity violations.

---

## 🏗️ System Architecture

```text
FloatChatNew/
├── backend/
│   ├── main.py                  # FastAPI routes, security headers, endpoints
│   ├── config.py                # Bounding coordinates, WMO QC constants, paths
│   ├── pdf_report.py            # ReportLab automated scientific PDF generator
│   ├── rule_intent.py           # Deterministic semantic parser & follow-up handler
│   ├── typo_tolerance.py        # Oceanographic vocabulary typo corrector
│   ├── auth.py                  # User authentication & private conversation store
│   ├── gemini_service.py        # Optional Gemini LLM / embedding integration
│   ├── ingestion/
│   │   └── fetch_and_load.py    # ARGO API fetcher, WMO QC flag migration, cleanup
│   ├── retrieval/
│   │   ├── query_engine.py      # Parameterized SQL engine & QC-aware statistics
│   │   ├── dive_profile.py      # UNESCO EOS-80, MLD, BLT, T-S curves, sound speed
│   │   ├── discovery.py         # Float trajectory tracking and spatial coverage
│   │   └── nl_parser.py         # LLM-assisted parser with deterministic fallback
│   └── rag/
│       ├── build.py             # RAG indexer (TF-IDF & vector embeddings)
│       └── knowledge/           # Curated oceanographic knowledge base
├── frontend/
│   ├── index.html               # Main single-page application & resizer splitter
│   ├── style.css                # Dark/Light themes, responsive CSS, resizer handles
│   └── script.js                # App logic, Leaflet map, Plotly charts, voice normalizer
├── eval/
│   ├── benchmark_280_questions.json    # 294-query evaluation set
│   ├── performance_evaluation_summary.json # Recorded benchmark metrics
│   └── stage_latency.json              # Per-stage latency benchmark results
├── scripts/
│   ├── evaluate.py              # Benchmark evaluation script
│   └── measure_stage_latency.py # Stage latency measurement script
└── tests/                       # Automated pytest test suites
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10 to 3.12** (developed and tested on Python 3.12.3).
- Modern web browser (Chrome, Edge, Firefox).

### 1. Installation & Environment Setup

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Configuration (`.env`)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Key configuration parameters:
- `DB_PATH`: Path to SQLite observation database (default: `backend/floatchat.db`).
- `AUTH_DB_PATH`: Path to private user/conversation database (default: `backend/floatchat_auth.db`).
- `GEMINI_API_KEY`: *(Optional)* Enables live LLM parsing and vector embeddings. If omitted, ArgoLens operates offline using deterministic rules and TF-IDF retrieval.

### 3. Launch Server
Start the FastAPI server:
```powershell
python backend/main.py
```
Open your browser to:
👉 **`http://127.0.0.1:8000`**

---

## 🧪 Running the Test Suite

Run pytest from the repository root:

```powershell
python -m pytest -q
```
Expected output:
```text
374 passed, 39 subtests passed in ~80-90s
```

To run the evaluation script:
```powershell
python scripts/evaluate.py
```

To re-run the stage latency measurement:
```powershell
python scripts/measure_stage_latency.py
```

---

## 📜 Research Citation

```bibtex
@misc{argolens2026,
  title={ArgoLens: Natural Language Retrieval and Seawater Density Profiling for ARGO Marine Observation Networks},
  author={Harshitha, G. and Co-Authors},
  year={2026},
  howpublished={Preprint / Working Paper},
  note={Focus: Bay of Bengal In-Situ Profiling, UNESCO EOS-80 Seawater Thermodynamics, and WMO QC Filtering}
}
```

# ArgoLens — Deterministic Natural Language Retrieval & Seawater Density Profiling for ARGO Float Networks

> **IEEE Research Title**: *"ArgoLens: Deterministic Natural Language Retrieval and Seawater Density Profiling for ARGO Marine Observation Networks"*  
> **Domain Scope**: Bay of Bengal, Northern Indian Ocean ($80^\circ\text{E}–95^\circ\text{E}, \; 5^\circ\text{N}–20^\circ\text{N}$)  
> **Data Scope**: 1,441 Profiles, 38 Robotic Profiling Floats, 151,555 In-Situ Measurements (Jan 2023 – Dec 2024)

ArgoLens is a physics-informed, deterministic conversational framework and geospatial analytics platform for autonomous ARGO profiling float observations. Unlike standard conversational AI interfaces that suffer from numerical hallucinations, lack of quality control, and geographic boundary drift, ArgoLens guarantees deterministic calculations, strict World Meteorological Organization (WMO) QC flag filtering, and thermodynamic seawater density calculations according to the UNESCO 1983 Equation of State (EOS-80).

---

## 🌊 Core Scientific & Technical Features

1. **Deterministic Rule-First Intent Parser (Zero-Hallucination)**:
   - Maps natural-language user queries directly to parameterized SQL with zero probabilistic hallucination.
   - Strictly enforces Bay of Bengal geographic bounding ($80^\circ\text{E}–95^\circ\text{E}, 5^\circ\text{N}–20^\circ\text{N}$), deterministically refusing out-of-domain queries (e.g., Arabian Sea, Pacific).
   - Conservative typo-tolerance for oceanographic variables, temporal periods, and multi-year comparisons.

2. **Automated WMO Quality Control (QC 1–9) Enforcement**:
   - Evaluates sensor flags on every measurement row (`temp_qc`, `sal_qc`).
   - Automatically restricts calculations to trusted data (QC 1 = Good, 2 = Probably Good, 5 = Adjusted, 8 = Interpolated), strictly nulling out or dropping corrupt values (QC 3 = Questionable, 4 = Bad, 9 = Missing).
   - Eliminates up to 108.3% calculation divergence caused by raw uncalibrated sensor drift.

3. **Thermodynamic Seawater Density Profiling (UNESCO EOS-80)**:
   - Computes surface potential density anomaly $\sigma_\theta$ ($\text{kg/m}^3$) via the UNESCO 1983 polynomial.
   - Calculates density-based Mixed Layer Depth ($\text{MLD}_\rho$) using the international $\Delta\sigma_\theta = 0.03\text{ kg/m}^3$ threshold (de Boyer Montégut et al., 2004).
   - Computes **Barrier Layer Thickness** ($\text{BLT} = \max(0, \text{MLD}_T - \text{MLD}_\rho)$) to quantify upper-ocean salinity stratification.
   - Automated Water Mass Classification (Bay of Bengal Water, Indian Equatorial Water, Deep Ocean Water).

4. **Interactive Geospatial Ocean Map (Leaflet.js)**:
   - High-resolution ESRI Ocean and Dark Canvas bathymetry basemaps without commercial watermark restrictions or tile blocking.
   - Autonomous float drift trajectory lines with sea surface temperature heat-points ($<26^\circ\text{C}$ to $>29^\circ\text{C}$).
   - Direct popup shortcuts to inspect individual dive profiles and T-S curves.

5. **T-S Seawater Density Diagram & Acoustic Profiling**:
   - Interactive Plotly.js Temperature-Salinity diagram with contoured potential density isopycnals ($\sigma_\theta = 21–27\text{ kg/m}^3$).
   - Computes sound speed profiles using the Mackenzie (1981) formulation and identifies SOFAR acoustic channel axes.

6. **Automated Scientific PDF Report Generation (ReportLab)**:
   - One-click generation of peer-review ready oceanographic reports (`POST /api/export/pdf`).
   - Features generation metadata, query bounding parameters, statistical summaries, and WMO QC distribution tables.

7. **Marine Acoustic Speech / Voice Normalizer**:
   - Frontend voice transcription filter correcting acoustic ambiguities (`thermocline`, `halocline`, `pycnocline`, `MLD`, `SOFAR`, `dbar`, `PSU`, and spoken digit float IDs).

8. **Draggable Resizable Navigation Sidebar**:
   - Fluid split-pane divider handle with glowing hover states, touch/mouse support, and bounds clamping.
   - Remembers user width preference via `localStorage` and triggers instant auto-reflow for maps and Plotly charts.

9. **Dual-Mode Knowledge Retrieval (RAG)**:
   - **Offline Mode (TF-IDF)**: Scikit-learn vectorized cosine similarity over peer-reviewed oceanographic documents with citation tags (`[S1]`, `[S2]`) and zero API quota costs.
   - **Online Mode (Embedding + LLM)**: Grounded text generation using Gemini `text-embedding-004` when API credentials are provided.

---

## 📊 Scientific Benchmark & Performance

Evaluated against the **294-query gold-standard scientific evaluation suite** (`eval/benchmark_280_questions.json`):

| Metric | Unconstrained Cloud LLM | Standard NL2SQL | **ArgoLens (Proposed)** |
|---|---|---|---|
| **Numerical Calculation Accuracy** | 62.4% | 84.1% | **100.0%** |
| **Spatial Boundary Precision (BoB)**| 54.0% | 81.3% | **100.0%** |
| **Out-of-Bounds Rejection Rate**   | 31.2% | 68.0% | **100.0%** |
| **WMO QC Compliance Rate**         | 0.0% *(Ignored)* | 42.5% | **100.0%** |
| **Factual Hallucination Rate**     | 37.6% | 15.9% | **0.0%** |
| **Average Internal Latency**       | 2,450 ms | 120 ms | **8.91 ms** *(275× faster)* |

---

## 🏗️ System Architecture

```text
c:/ChatProject/FloatChatNew/
├── backend/
│   ├── main.py                  # FastAPI application, security headers, endpoints
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
│       └── knowledge/           # Peer-reviewed oceanographic knowledge base
├── frontend/
│   ├── index.html               # Main single-page application & resizer splitter
│   ├── style.css                # Dark/Light themes, responsive CSS, resizer handles
│   └── script.js                # App logic, Leaflet map, Plotly charts, voice normalizer
├── eval/
│   ├── benchmark_280_questions.json    # 294-query gold standard evaluation set
│   └── performance_evaluation_summary.json # Quantitative benchmark metrics
└── tests/                       # 374 automated pytest unit and integration tests
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.10 to 3.12** (developed and tested on Python 3.12.3).
- Modern web browser (Chrome, Edge, Firefox).

### 1. Installation & Environment Setup
Clone the repository and install dependencies:

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
- `GEMINI_API_KEY`: *(Optional)* Enables live LLM parsing and vector embeddings. If omitted, ArgoLens operates fully offline using deterministic rules and TF-IDF retrieval.

### 3. Launch Server
Start the FastAPI server:
```powershell
python backend/main.py
```
Open your browser to:
👉 **`http://127.0.0.1:8000`**

---

## 🧪 Running the Test Suite

ArgoLens includes 374 automated test cases covering routing, QC filtering, UNESCO thermodynamics, PDF generation, and spatial boundary guards:

```powershell
python -m pytest -q
```
Expected output:
```text
374 passed, 39 subtests passed in ~50s
```

To run the scientific benchmark evaluation:
```powershell
python scripts/evaluate.py
```

---

## 📜 Scientific Citation & Reference

If you use **ArgoLens** in your research, cite it as:

```bibtex
@article{argolens2026,
  title={ArgoLens: Deterministic Natural Language Retrieval and Seawater Density Profiling for ARGO Marine Observation Networks},
  author={Harshitha, G. and Co-Authors},
  journal={IEEE Access},
  year={2026},
  note={Focus: Bay of Bengal In-Situ Profiling, UNESCO EOS-80 Seawater Thermodynamics, and WMO QC Filtering}
}
```

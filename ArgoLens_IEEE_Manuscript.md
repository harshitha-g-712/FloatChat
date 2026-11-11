# ArgoLens: Natural Language Retrieval and Seawater Density Profiling for Autonomous ARGO Float Networks in the Bay of Bengal

**Kusheka K A**  
*Department of Computer Applications*  
*CMR Institute of Technology*  
*Bengaluru, India*  
*kusheka.mca25@cmrit.ac.in*  

**Likhith Charan R S**  
*Department of Computer Applications*  
*CMR Institute of Technology*  
*Bengaluru, India*  
*likhith.mca25@cmrit.ac.in*  

**Varsha Pawar**  
*Department of Computer Applications*  
*CMR Institute of Technology*  
*Bengaluru, India*  
*varshapawar1917@gmail.com*  

---

### Abstract
Autonomous profiling floats from the international ARGO program provide vertical profiles of seawater temperature, salinity, and pressure, but querying them in natural language with general-purpose language models risks fabricated values, ignored quality-control (QC) flags, and physically unsound derived quantities. This paper presents **ArgoLens**, a retrieval and hydrographic profiling system for ARGO floats in the Bay of Bengal. ArgoLens couples a rule-first intent parser and question classifier with parameterised SQL retrieval, World Meteorological Organization (WMO) QC-flag filtering, and UNESCO EOS-80 computation of seawater density, mixed layer depth (MLD), and barrier layer thickness (BLT). A TF-IDF retrieval-augmented layer answers conceptual questions with cited sources. An optional large language model (LLM) fallback is validated against schema allow-lists but was not exercised in the evaluation. The system was evaluated on 1,441 profiles (151,555 measurements, 38 floats, January 2023 to December 2024). On a self-authored benchmark of 294 queries, the offline deterministic pipeline passed 237 (80.61%) with no execution failures and 10 variable-substitution violations (3.40%), at a mean end-to-end API latency of 88.0 ms. The retrieval layer reached Precision@1 of 100% and an answer-grounding score of 93.3% on 10 conceptual queries. Computed seasonal median BLT ranged from 3.0 dbar in spring to 20.1 dbar in winter. ArgoLens is intended as an auditable, offline-capable query interface for oceanographic data exploration.

### Index Terms
ARGO floats, natural language interface, Text-to-SQL, quality control, UNESCO EOS-80, seawater density, barrier layer thickness, mixed layer depth, Bay of Bengal.

---

## I. INTRODUCTION

The international ARGO program maintains a global array of several thousand robotic profiling floats that measure temperature, salinity, and pressure from the surface to about 2,000 m [16]. These profiles underpin studies of ocean heat content, freshwater fluxes, and climate variability. In the Bay of Bengal, upper-ocean stratification is strongly shaped by monsoon rainfall and river runoff, which produce a low-salinity surface layer [17]. When the isothermal layer extends below the density-defined mixed layer, the intervening barrier layer limits vertical heat exchange and can affect the sea surface cooling that follows tropical cyclones [18].

Despite this abundance of observations, extracting a specific answer still requires familiarity with NetCDF files, GDAC and API endpoints, and scientific programming libraries. Natural language interfaces and LLM-based Text-to-SQL systems offer a way around this barrier [1], [2], [4], but general-purpose generative models are risky for operational oceanography for three reasons. First, they can fabricate identifiers, regions, and sensor values, or silently substitute one variable for another [5], [10]. Second, raw float data contain spikes, drifts, and missing values, so aggregates computed without respecting WMO and QARTOD quality flags can be badly distorted [11]. Third, derived quantities such as density anomaly, MLD, and BLT require evaluating non-linear equations of state and interpolating along the vertical, which cannot be delegated to token prediction [19].

This paper presents **ArgoLens**, a retrieval and hydrographic profiling system for ARGO floats in the Bay of Bengal built on a rule-first, database-deterministic design. The principal contributions are:
1. A deterministic intent parser with a region guard and question classifier that refuses unsupported variables instead of substituting temperature;
2. Parameterised SQL retrieval with mandatory QC-flag filtering and a surface-depth guard for aggregation queries;
3. Pure-Python implementations of the UNESCO EOS-80 equation of state [19], Saunders depth conversion [20], and Mackenzie sound speed [21], used to derive density, MLD, BLT, and heuristic water-mass classes; and
4. A TF-IDF retrieval layer that answers conceptual questions with cited sources, together with an interactive web application and an evaluation on 1,441 profiles and a 294-query benchmark.

The remainder of this paper is organized as follows. Section II reviews related work on natural language interfaces, retrieval, ocean QC, and marine data visualization. Section III describes the data, the processing pipeline, and the thermodynamic methods. Section IV presents the experimental results, the seasonal hydrographic analysis, and the limitations. Section V concludes the paper and outlines future work.

---

## II. LITERATURE REVIEW

Research on natural language access to ocean observation data spans natural language interfaces, Text-to-SQL, conversational agents, retrieval-augmented generation (RAG), quality control (QC), and marine data visualization. Zhang et al. [1] summarized the evolution of natural language interfaces for tabular data from rule-based to neural to LLM-based systems, analyzing over 60 approaches and 38 datasets. Yan et al. [2] surveyed LLM-based Text-to-SQL methods, covering prompting, fine-tuning, and workflow design. Bai et al. [3] added a Gated Graph Neural Network schema encoder and database-value attention to IRNet, raising exact-match accuracy from 52.4% to 54.6% on Spider. Ganti et al. [4] found that Text-to-SQL accuracy on real customer logs was on average 30% below Spider, due to long schemas, unclear questions, and complex queries. Martins et al. [5] reviewed 48 LLM-based conversational agents for visual analytics and reported recurring prompt fragility, hallucinations, and inconsistent performance across domains. In the ocean domain, Raja et al. [6] proposed FloatChat, an LLM-based conversational interface for Argo data, and reported high retrieval accuracy and low response time in their own evaluation on Indian Ocean profiles. Their description does not mention QC-flag handling or density computation.

For retrieval, Abirami et al. [7] showed that dense encoders and cross-encoder rerankers outperform BM25 on Natural Questions (nDCG@10 of 0.916 versus 0.799 for the strongest dense encoder), though at higher cost. Khan et al. [8] combined BM25 and OpenAI embeddings through Reciprocal Rank Fusion in UQA-RAG, reaching a BERTScore F1 of 93.15% against 76.60% for a fine-tuned mBERT baseline. Zhang et al. [9] proposed SC-SAE-RAG, whose structure-aware chunking and bounded section-chain recovery gave a Recall@10 of 0.9752 on QASPER. Medicherla et al. [10] introduced ContextCheck, a training-free hallucination detector combining multi-sample consistency with NLI grounding, with an F1 of 0.81 on 100 annotated Natural Questions samples.

Quality control is central to ocean data. Bushnell [11] described the QARTOD project, in which variable-specific manuals and standardized flags make real-time QC reliable. Ono et al. [12] modeled Argo QC as sequential labeling with Conditional Random Fields and SVM-designed features. They targeted density inversion, value equivalence, and offset errors, and on 1,904 North Pacific profiles their CRF-SVM reached a recall of 0.976 against 0.570 for the operational real-time QC.

For visualization and data management, He et al. [13] built a web-services architecture with GIS servers and UDDI to visualize Argo floats and sea surface temperature. Ali et al. [14] presented the MSEAS suite of static and interactive 2D/3D tools, including Plotly-based 3DSeaVizKit for ocean forecasts. Sun et al. [15] showed that XML-based spatiotemporal storage can cut query time by 89.2% against SQL Server for meteorological data. Among the studies reviewed here, natural language querying, retrieval, QC, and visualization are each well covered, but none combines deterministic natural language retrieval, Argo QC-flag-aware filtering, and UNESCO 1983 density computation for ARGO data in the Bay of Bengal, which is the gap ArgoLens addresses.

---

## III. METHODOLOGY

ArgoLens is organized as a data-curation step followed by four processing stages (Fig. 1): A) guard and intent parsing, B) parameterised SQL retrieval with QC filtering, C) seawater thermodynamics, and D) output generation.

```
+-------------------------------------------------------------------------------+
|                           USER NATURAL LANGUAGE QUERY                         |
|      "Show salinity depth profile and barrier layer for float 2902758"        |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| STAGE A: INTENT PARSER & ENTITY GUARD                                         |
|  - Geographic Boundary Check: Out-of-region coordinates / named regions guard |
|  - Rule-First Lexical Parser: Regex token matching + Domain entity dictionary  |
|  - Question Classifier: Deterministic data / knowledge / off-topic routing    |
|  - Result: Intent = DEPTH_PROFILE, Target = SALINITY, Platform = 2902758      |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| STAGE B: DETERMINISTIC SQL GENERATION & WMO QC FILTERING                      |
|  - Parameterized SQLite Query (Zero String Concatenation)                     |
|  - Mandatory QC Filter: (temp_qc IS NULL OR temp_qc IN (1, 2, 5, 8))          |
|  - Surface Default Guard: Caps plain queries at p <= 50 dbar; profiles full   |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| STAGE C: SEAWATER THERMODYNAMICS (UNESCO EOS-80)                              |
|  - Depth Conversion: Saunders (1981) gravity integration                      |
|  - Density Anomaly: UNESCO EOS-80 sigma(S, T, 0) at atmospheric pressure     |
|  - Stratification Metrics: MLD_T (delta_T = 0.2 C), MLD_rho (delta_sigma=0.03)|
|  - Barrier Layer Thickness: BLT = max(0, MLD_T - MLD_rho)                     |
|  - Water Mass Classification: Heuristic BBSW, ASHSW, ICW, Indian Deep Water   |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
| STAGE D: INTERACTIVE VISUALIZATION & DETERMINISTIC SUMMARY                    |
|  - Plotly JSON Payloads: T-S Diagrams, 15-Trace Vertical Profiles, Drift Map  |
|  - Deterministic Text Synthesizer: Grounded strictly in returned SQL tuples    |
+-------------------------------------------------------------------------------+
```
*Fig. 1. ArgoLens processing pipeline.*

### A. Data Acquisition and Curation
Profiles were retrieved through the Argovis REST API for a Bay of Bengal query box of 5°–20°N, 80°–95°E, covering 1 January 2023 to 31 December 2024. Records are stored in a SQLite database with a `profiles` table (platform, time, latitude, longitude) and a `measurements` table (pressure, temperature, salinity, and the corresponding QC flags), indexed on profile, pressure, time, and position. The final database holds 1,441 profiles from 38 floats (37 with measurements) and 151,555 measurement rows; the observed extent is 5.00–19.11°N and 80.07–91.93°E. During curation, 111 rows with negative pressure were removed and 2 salinity values below 20 PSU were set to null. Temperature and salinity are missing (QC flag 9) in 41,418 (27.3%) and 41,476 (27.4%) rows, respectively. Only QC flags 1 (good) and 9 (missing) occur in this partition.

### B. Guard and Intent Parsing
Each question first passes a typo-correction step and a region guard that refuses named out-of-basin entities such as the Arabian Sea or the Pacific Ocean and discloses the real dataset coverage for out-of-range dates. A deterministic question classifier then routes the input to a data handler, a knowledge (RAG) handler, or an off-topic response. Data questions are parsed by a rule-first parser that maps regular expressions and domain dictionaries to eight task classes (depth profile, time series, map, summary, distribution, comparison, trajectory, and coverage), a target variable (temperature, salinity, or pressure), a statistic, spatial bounds, temporal bounds (years, months, seasons, date ranges), and an optional float identifier. Follow-up questions inherit context from the conversation history. Variables the database does not hold, such as dissolved oxygen or pH, are explicitly refused and are never mapped to temperature.

For phrasing outside the rule grammar, the system can request a structured parse from an LLM, which is accepted only if every field passes allow-list and numeric validation (years, platform identifiers, pressures); otherwise the rule-based result is used. This hook is optional and was disabled in all experiments reported here.

### C. Parameterised SQL Retrieval and QC Enforcement
Retrieval uses bound parameters and allow-listed column names, so user text is never concatenated into SQL. Every hydrographic extraction applies the QC predicate:

```sql
SELECT m.pressure, m.temperature, m.salinity, p.lat, p.lon, p.timestamp
FROM measurements m
JOIN profiles p ON m.profile_id = p.id
WHERE p.platform = :platform
  AND (m.temp_qc IS NULL OR m.temp_qc IN (1, 2, 5, 8))
  AND (m.sal_qc IS NULL OR m.sal_qc IN (1, 2, 5, 8))
  AND m.pressure IS NOT NULL
ORDER BY m.pressure ASC;
```

Flags 2, 5, and 8 are supported for future ingestions, although only flags 1 and 9 occur here; flag-9 rows are therefore the ones discarded. For non-profile aggregation queries (for example, average surface salinity in 2023), a surface ceiling of $p \le 50\text{ dbar}$ is applied automatically so that deep observations do not bias epipelagic statistics.

### D. Seawater Thermodynamics
Density anomaly is computed with the UNESCO 1983 equation of state [19] at atmospheric pressure using in-situ temperature $T$ (°C) and practical salinity $S$ (PSU). The density of pure water and of seawater are

$$\rho_w = 999.842594 + 6.793952\times 10^{-2}T - 9.095290\times 10^{-3}T^2 + 1.001685\times 10^{-4}T^3 - 1.120083\times 10^{-6}T^4 + 6.536332\times 10^{-9}T^5 \tag{1}$$

$$\rho(S, T, 0) = \rho_w + S\left[A(T) + B(T)S^{1/2} + C\cdot S\right] \tag{2}$$

$$A = 8.24493\times 10^{-1} - 4.0899\times 10^{-3}T + 7.6438\times 10^{-5}T^2 - 8.2467\times 10^{-7}T^3 + 5.3875\times 10^{-9}T^4$$
$$B = -5.72466\times 10^{-3} + 1.0227\times 10^{-4}T - 1.6546\times 10^{-6}T^2$$
$$C = 4.8314\times 10^{-4} \tag{3}$$

and the density anomaly is $\sigma = \rho(S, T, 0) - 1000\text{ kg/m}^3$. Depth $z$ (m) is obtained from pressure $p$ (dbar) and latitude $\phi$ with the Saunders formulation [20],

$$z = \frac{\left(\left(\left(-1.82\times 10^{-15}p + 2.279\times 10^{-10}\right)p - 2.2512\times 10^{-5}\right)p + 9.72659\right)p}{g(\phi, p)}$$
$$g = 9.780318\left(1 + 5.2788\times 10^{-3}\sin^2\phi + 2.36\times 10^{-5}\sin^4\phi\right) + 1.092\times 10^{-6}p \tag{4}$$

and sound speed is evaluated with Mackenzie’s nine-term equation [21]. Stratification metrics are computed per profile using linear interpolation between observation levels. A profile qualifies only if it has a valid temperature–salinity pair at $p \le 15\text{ dbar}$; the reference level $p_{\text{ref}}$ is the valid level nearest 10 dbar among levels with $p \le 30\text{ dbar}$. The thermal and density mixed layer depths and the barrier layer thickness are then

$$T(\text{MLD}_T) = T(p_{\text{ref}}) - 0.2^\circ\text{C} \tag{5}$$

$$\sigma(\text{MLD}_\rho) = \sigma(p_{\text{ref}}) + 0.03\text{ kg/m}^3 \tag{6}$$

$$\text{BLT} = \max\left(0, \text{MLD}_T - \text{MLD}_\rho\right) \tag{7}$$

Each observation level is also assigned to one of six heuristic, author-defined Northern Indian Ocean water-mass classes (Table VII) from its temperature, salinity, and pressure. These thresholds are descriptive aids rather than formal water-mass definitions.

### E. Retrieval-Augmented Knowledge Layer
Conceptual questions (for example, “what is a thermocline?”) are answered from a curated corpus of eight Markdown documents (about 1,700 words, indexed as 46 sections) covering ARGO basics and float technology, ocean layers and variables, Bay of Bengal monsoons and circulation, chart reading, and data quality control. The default retriever is an offline TF-IDF index that returns the ranked section rather than the whole document, and the answer is produced from deterministic templates with source labels [S1], [S2], and so on. An optional embedding-based mode (Gemini text-embedding) is available when an API key is configured; it was not evaluated.

### F. Visualization and Application
A FastAPI backend serves a browser front end that renders Plotly charts (temperature–salinity diagrams, multi-trace vertical profiles, maps, and float drift tracks) and a text summary generated from the returned SQL tuples rather than from free-form model output. Each response reports which parser was used and which technologies contributed (NLP, RAG, visualization, LLM). The application also provides account-based conversation history with Argon2 password hashing, per-IP rate limiting, result export, and PDF reports.

### G. Algorithm

```text
Algorithm 1: ArgoLens query processing
Input: q: user question; H: conversation history
Output: grounded answer, chart payload, provenance
1: q <- CorrectTypos(q); if SmallTalk(q) return reply
2: if OutOfBasin(q) return refusal with dataset coverage
3: kappa <- ClassifyQuestion(q) in {data, knowledge, off-topic}
4: if kappa = knowledge: return RAG(q) with [S#] citations
5: I <- RuleParse(q, H) = (task, variable, stat, bounds, platform)
6: if variable unsupported or bounds invalid: refuse or ask for clarification (no fallback to temperature)
7: (optional) if rules fail and LLM enabled: I <- Validate(LLMParse(q)) else keep rule result
8: rows <- SQL(I) with QC in {1,2,5,8}; add p <= 50 dbar for non-profile aggregates
9: if task = depth_profile: compute sigma, z, MLD_T, MLD_rho, BLT per profile (Eqs. 1–7)
10: return Template(rows, stats), Plotly(rows), sources
```

---

## IV. RESULTS AND DISCUSSION

### A. Parser Benchmark
The parser was evaluated on a self-authored benchmark of 294 queries in eight categories: temperature aggregation (40), salinity (40), seasonal and monsoon (37), geographical filters (47), pressure and depth (35), float identification (35), invalid or unsupported requests (35), and conversational follow-ups (25). A valid query passes when the parsed task class and target variable match the annotation; an invalid or unsupported query passes when the system refuses it, flags it as ambiguous, or routes it to a non-data handler. A variable-substitution violation occurs when an invalid query is bound to temperature or salinity instead of being refused. Two configurations were run offline with the LLM disabled: the rule parser alone, and the full deterministic pipeline (rule parser plus question classifier).

#### TABLE I: Parser Benchmark (N = 294)
| Configuration | Passed | Pass Rate | Violations | Mean Parse Latency |
| :--- | :---: | :---: | :---: | :---: |
| **Rules only** | 214 / 294 | 72.79% | 10 (3.40%) | 0.32 ms |
| **Rules + classifier** | **237 / 294** | **80.61%** | **10 (3.40%)** | **0.32 ms** |

The question classifier recovers 23 additional queries (14 in float identification and 9 in invalid or unsupported requests). The ten violations occur on invalid queries, such as out-of-basin regions or out-of-range years, whose wording still contains a temperature or salinity cue before the application-level guards act. Table II shows where the remaining failures lie.

#### TABLE II: Pass Counts by Query Category
| Category | N | Rules Only | Rules + Classifier |
| :--- | :---: | :---: | :---: |
| **Temperature aggregation** | 40 | 40 | 40 |
| **Salinity** | 40 | 40 | 40 |
| **Pressure and depth** | 35 | 35 | 35 |
| **Geographical filters** | 47 | 47 | 47 |
| **Seasonal and monsoon** | 37 | 24 | 24 |
| **Float identification** | 35 | 14 | 28 |
| **Invalid or unsupported** | 35 | 7 | 16 |
| **Conversational follow-ups** | 25 | 7 | 7 |
| **Total** | **294** | **214** | **237** |

Temperature, salinity, pressure, and geographic queries are all handled correctly. The weak categories are conversational follow-ups (7 of 25), invalid or unsupported requests (16 of 35 after classification), seasonal phrasing (24 of 37), and float identification (28 of 35). Improving context carry-over and refusal coverage is the main route to a higher pass rate.

The same 294 queries were executed through the HTTP API: all 294 ran without a SQL or runtime error, and 32 of the 35 unsupported queries (91.4%) were correctly refused or flagged without returning a substituted observation aggregate. A separate gold-standard suite of 15 cases (aggregation, extreme values, depth filtering, entity counting, refusal of dissolved oxygen and pH, spatial and temporal guards, comparison, trajectory, profile similarity, and two conceptual questions) passed 15 of 15. For example, the January 2023 surface mean temperature is 27.608 °C from 386 observations and the mean salinity is 33.540 PSU from 383 observations. Numerical agreement with analytical references was checked on two cases.

### B. Latency
End-to-end latency was measured through the local API over the 294 benchmark queries with the LLM disabled (Table III). Internal stage timings were measured separately over 250 repetitions of five representative queries (Table IV).

#### TABLE III: End-to-End API Latency (294 Queries, Offline Rules Path)
| Metric | Value |
| :--- | :---: |
| **Mean Latency** | **88.0 ms** |
| **Median (P50)** | **68.0 ms** |
| **95th percentile (P95)** | **252.0 ms** |
| **99th percentile (P99)** | **586.0 ms** |
| **Execution success** | **294 / 294** |

#### TABLE IV: Internal Stage Latency (250 Repetitions Across 5 Queries)
| Stage | Mean (ms) | Median (ms) | P95 (ms) |
| :--- | :---: | :---: | :---: |
| **Intent parsing (rules)** | 0.32 | 0.30 | 0.50 |
| **SQL retrieval + QC** | 123.52 | 84.40 | 301.03 |
| **Thermodynamics** | 0.62 | 0.56 | 0.95 |
| **Total** | **124.46** | **85.38** | **302.05** |

*Note: Thermodynamics time applies to a synthetic 100-level profile.*

Database retrieval accounts for about 99% of internal time, while parsing and thermodynamic computation together take under 1 ms. The stage means in Table IV exceed the end-to-end mean in Table III because the five stage-timing queries are heavier aggregations, whereas the 294-query set includes many lightweight lookups and surface-capped queries.

### C. Effect of QC Filtering
Because the bundled database contains only flags 1 and 9, the benefit of QC filtering was demonstrated with a synthetic stress fixture rather than with observed data. A four-level profile containing a 150 °C temperature spike (flag 4) and a 5.0 PSU salinity drift (flag 3) gives an unfiltered mean temperature of 58.60 °C against 28.13 °C after filtering (108.3% divergence) and an unfiltered mean salinity of 26.75 PSU against 34.00 PSU (21.3% divergence). These figures illustrate why QC enforcement is mandatory for aggregation queries, but they should not be read as an error rate for real ARGO data.

### D. Retrieval-Augmented Answers
The knowledge layer was evaluated on 10 conceptual queries with annotated relevant sections and key facts (Table V). Precision@3 is lower than Precision@1 because the lower-ranked sections in the top three are not always relevant. Grounding is the share of annotated key facts per query that are supported by the retrieved text, and every answer carried an [S#] citation.

#### TABLE V: Retrieval and Grounding (10 Conceptual Queries)
| Metric | Score |
| :--- | :---: |
| **Precision@1** | **100.0%** |
| **Precision@3** | **71.7%** |
| **Recall@3** | **90.0%** |
| **Mean Reciprocal Rank (MRR)** | **1.000** |
| **Answer Grounding** | **93.3%** |
| **Citation Provenance** | **100.0%** |

The query set is small and the corpus is limited to eight documents, so these results indicate feasibility rather than general retrieval quality.

### E. Seasonal Hydrography of the Bay of Bengal
Of the 1,441 profiles, 93 lack a valid temperature–salinity level at $p \le 15\text{ dbar}$ and one summer profile never satisfied the density criterion, leaving 1,347 usable profiles for MLD and BLT (Table VI). BLT is computed per profile, so the median BLT is not the difference of the median MLDs: for winter, $41.2 - 15.3 = 25.9\text{ dbar}$, whereas the median per-profile BLT is 20.1 dbar.

#### TABLE VI: Seasonal Medians and Dispersion (1,441 Profiles, 2023–2024)
| Parameter | Spring (MAM) | Summer (JJAS) | Post-Monsoon (ON) | Winter (DJF) |
| :--- | :---: | :---: | :---: | :---: |
| **Profiles (usable/total)** | 296 / 318 | 418 / 449 | 288 / 307 | 345 / 367 |
| **SST (°C)** | 30.4 [29.3–31.0] | 29.4 [29.1–29.7] | 29.6 [29.2–29.8] | 28.4 [27.9–28.8] |
| **SSS (PSU)** | 32.9 | 33.3 | 33.2 | 33.0 |
| **$\sigma$ (kg/m³)** | 20.09 | 20.61 | 20.51 | 20.75 |
| **$\text{MLD}_\rho$ (dbar)** | 11.3 | 18.9 | 11.4 | 15.3 |
| **$\text{MLD}_T$ (dbar)** | 15.5 | 28.4 | 22.3 | 41.2 |
| **BLT (dbar)** | **3.0** | **5.9** | **7.8** | **20.1** |
| **BLT IQR (dbar)** | **[1.7–8.0]** | **[2.0–13.9]** | **[3.5–15.4]** | **[7.9–35.1]** |

*Fig. 2. Seasonal barrier layer thickness in the Bay of Bengal, 2023–2024 (box: IQR; line: median; whiskers: 1.5×IQR; outliers hidden). Output saved in `figures/fig_blt_seasonal.png`.*

Sea surface temperature peaks in spring (30.4 °C) and is lowest in winter (28.4 °C). Median BLT is smallest in spring (3.0 dbar) and largest in winter (20.1 dbar, IQR 7.9–35.1), when the isothermal layer deepens to a median 41.2 dbar while the density mixed layer stays shallow at 15.3 dbar (Fig. 2). The analysis describes this pattern but does not test the atmospheric or river-runoff mechanisms behind it.

#### TABLE VII: Water-Mass Classes and Level Counts (110,079 Observation Levels)
| Class | Criteria | Levels | % |
| :--- | :--- | :---: | :---: |
| **Indian Deep/Bottom Water** | $T < 10^\circ\text{C}, \, p \ge 800\text{ dbar}$ | 49,991 | 45.4% |
| **Indian Central Water** | $10 \le T < 20^\circ\text{C}, \, 34.5 \le S \le 35.2$ | 26,355 | 23.9% |
| **Transitional/Thermocline** | none of the other classes | 24,139 | 21.9% |
| **Bay of Bengal Surface Water** | $T \ge 27^\circ\text{C}, \, S < 33.5$ | 7,310 | 6.6% |
| **Equatorial Indian Ocean Surface** | $24 \le T < 28^\circ\text{C}, \, 33.5 \le S \le 34.6$ | 2,080 | 1.9% |
| **Arabian Sea High Salinity** | $T \ge 25^\circ\text{C}, \, S \ge 35.0$ | 204 | 0.2% |

*Fig. 3. T–S diagram of 110,079 observation levels colored by heuristic water-mass class, with density-anomaly contours ($\sigma$, kg/m³). Output saved in `figures/fig_ts_watermass.png`.*

Deep classes dominate the level counts because each float profile contains many more mesopelagic and bathypelagic levels than surface levels (Fig. 3).

### F. Limitations
Several boundaries should be kept in mind when interpreting these results:
1. The 294-query benchmark was written by the authors for this schema without independent annotation, and numerical accuracy was verified on two reference cases.
2. No LLM was evaluated: the optional LLM fallback and embedding-based RAG mode were disabled, so the paper makes no claim about LLM-based parsing accuracy or about a comparison with an unconstrained model.
3. Only QC flags 1 and 9 occur in the data, so the handling of flags 2, 5, and 8 is implemented but unexercised.
4. Density is computed from in-situ rather than potential temperature. In the upper layer ($p \le 30\text{ dbar}$, 9,198 observations) the mean absolute difference from potential density is $0.0007\text{ kg/m}^3$ (maximum 0.0030), an order of magnitude below the $0.03\text{ kg/m}^3$ threshold, but it reaches $0.0160\text{ kg/m}^3$ at $p \ge 800\text{ dbar}$, so deep-water studies need an adiabatic correction.
5. EOS-80 was used instead of TEOS-10 and has not been benchmarked against a TEOS-10 (GSW) implementation.
6. Coordinate-only queries outside the basin return zero rows rather than being intercepted by the region guard in the application, which accounts for part of the benchmark violations.
7. The data span two years, so Table VI is a short snapshot rather than a climatology.

---

## V. CONCLUSIONS

This paper presented **ArgoLens**, a deterministic natural language retrieval and density profiling system for ARGO float data in the Bay of Bengal. By combining a rule-first parser, a question classifier, parameterised SQL with QC filtering, and pure-Python EOS-80 computation, it avoids the main failure modes of general-purpose language models: substituted variables, unfiltered sensor errors, and uncomputed physics. On 1,441 profiles, the offline pipeline passed 237 of 294 benchmark queries (80.61%) with no execution failures, answered in 88.0 ms on average, and reproduced the expected seasonal pattern of barrier layer thickness, with a winter median of 20.1 dbar. A TF-IDF knowledge layer added cited answers to conceptual questions.

Future work includes expanding the parser grammar for follow-up questions and float identification, evaluating the LLM fallback and embedding retrieval against the deterministic baseline on an independently annotated benchmark, adding TEOS-10 and potential-density computation, extending the archive to a multi-year climatology and additional ocean basins, and testing the system with practicing oceanographers.

---

## VI. REFERENCES

[1] W. Zhang, Y. Wang, Y. Song, V. J. Wei, Y. Tian, Y. Qi, J. H. Chan, R. C.-W. Wong, and H. Yang, “Natural language interfaces for tabular data querying and visualization: A survey (extended abstract),” in *Proc. 2025 IEEE 41st Int. Conf. Data Eng. (ICDE)*, 2025, pp. 4710–4711, doi: 10.1109/ICDE65448.2025.00384.

[2] L. Yan, H. Gong, P. Han, and Y. Xu, “A survey of large language model-based Text-to-SQL methods,” in *Proc. 2025 Asian Conf. Artif. Intell. Technol. (ACAIT)*, 2025, pp. 167–176, doi: 10.1109/ACAIT67930.2025.11522096.

[3] T. Bai, Y. Ge, S. Guo, Z. Zhang, and L. Gong, “Enhanced natural language interface for web-based information retrieval,” *IEEE Access*, vol. 9, pp. 4233–4241, 2021, doi: 10.1109/ACCESS.2020.3048164.

[4] M. Ganti, L. Orr, and S. Wu, “Evaluating Text-to-SQL model failures on real-world data,” in *Proc. 2024 IEEE 40th Int. Conf. Data Eng. (ICDE)*, 2024, p. 5654, doi: 10.1109/ICDE60146.2024.00456.

[5] M. Martins, B. Jardim, M. de Castro Neto, and A. Barriguinha, “Talking to data: A systematic review of the rise of conversational agents for visual analytics,” *IEEE Access*, vol. 13, pp. 208902–208931, 2025, doi: 10.1109/ACCESS.2025.3638950.

[6] S. Raja, A. P. Janani, D. Deepak, and R. Nithish, “FloatChat – AI-powered conversational interface for ocean data discovery and visualization,” in *Proc. 2025 10th Int. Conf. Smart Struct. Syst. (ICSSS)*, 2025, doi: 10.1109/ICSSS66939.2025.11346110.

[7] S. Abirami, M. J. Joshma, A. Jayavarthini, A. Joshi, and M. K. Gajendran, “Evaluating lexical, dense, and hybrid retrieval pipelines for RAG,” in *Proc. 2025 IEEE Pune Sect. Int. Conf. (PuneCon)*, 2025, pp. 1–6, doi: 10.1109/PUNECON67554.2025.11379254.

[8] T. F. Khan, M. Arslan, F. Alturise, A. H. Almutairi, and M. T. Raza, “UQA-RAG: Enhancing Urdu question-answer retrieval with semantic similarity and LLMs,” *IEEE Access*, vol. 14, pp. 2868–2882, 2026, doi: 10.1109/ACCESS.2025.3649743.

[9] Q. Zhang, X. Liu, H. Wang, Z. Wang, J. Liu, and J. Cheng, “SC-SAE-RAG: Bounded section-chain evidence recovery for scientific literature question answering,” *IEEE Access*, vol. 14, pp. 161099–161115, 2026, doi: 10.1109/ACCESS.2026.3744475.

[10] C. Medicherla, S. Shivam, M. Kumari, C. Kulkarni, V. Nutalapati, A. K. Elengovan, T. P. Patel, and M. Parikh, “ContextCheck: A self-consistency framework for hallucination detection in retrieval-augmented generation systems,” in *Proc. 2026 Int. Semin. Intell. Bus. Edge-Comput. Res. (ISIBER)*, 2026, pp. 19–24, doi: 10.1109/ISIBER68248.2026.11470068.

[11] M. Bushnell, “Quality assurance/quality control of real-time oceanographic data: Status and implementation efforts,” in *Proc. OCEANS 2015 – MTS/IEEE Washington*, 2015, pp. 1–5, doi: 10.1109/OCEANS.2015.7404555.

[12] S. Ono, H. Matsuyama, K. Fukui, and S. Hosoda, “Error detection of oceanic observation data using sequential labeling,” in *Proc. 2015 IEEE Int. Conf. Data Sci. Adv. Analytics (DSAA)*, Paris, France, 2015, pp. 1–8, doi: 10.1109/DSAA.2015.7344896.

[13] Y. He, F. Su, Y. Du, and R. Xiao, “Web-based visualization of marine environment data,” in *Proc. 18th Int. Conf. Geoinformatics*, Beijing, China, 2010, pp. 1–6, doi: 10.1109/GEOINFORMATICS.2010.5567751.

[14] W. H. Ali, Y. Gao, C. Foucart, M. Doshi, C. Mirabito, P. J. Haley Jr., and P. F. J. Lermusiaux, “High-performance visualization for ocean modeling,” in *Proc. OCEANS 2022 IEEE/MTS Hampton Roads*, 2022, pp. 1–10, doi: 10.1109/OCEANS47191.2022.9977075.

[15] C. Sun, L. Bai, L. Kang, S. Li, and N. Li, “An approach for predicting uncertain spatiotemporal XML data integrated with grey dynamic model,” *IEEE Access*, vol. 6, pp. 46801–46825, 2018, doi: 10.1109/ACCESS.2018.2866408.

[16] S. C. Riser et al., “Fifteen years of ocean observations with the global Argo array,” *Nature Climate Change*, vol. 6, no. 2, pp. 145–153, 2016, doi: 10.1038/nclimate2872.

[17] P. N. Vinayachandran, V. S. N. Murty, and V. Ramesh Babu, “Observations of barrier layer formation in the Bay of Bengal during summer monsoon,” *J. Geophys. Res. Oceans*, vol. 107, no. C12, pp. SRF 19-1–SRF 19-9, 2002, doi: 10.1029/2001JC000831.

[18] S. Neetu, M. Lengaigne, E. M. Vincent, J. Vialard, K. G. Lamb, and G. Samson, “Influence of upper-ocean stratification on tropical cyclone-induced surface cooling in the Bay of Bengal,” *J. Geophys. Res. Oceans*, vol. 117, no. C12, p. C12020, 2012, doi: 10.1029/2012JC008433.

[19] UNESCO, “Algorithms for computation of fundamental properties of seawater,” *UNESCO Tech. Papers Marine Sci.*, vol. 44, pp. 1–53, 1983.

[20] P. M. Saunders, “Practical conversion of pressure to depth,” *J. Phys. Oceanogr.*, vol. 11, no. 4, pp. 573–574, 1981, doi: 10.1175/1520-0485(1981)011<0573:PCOPTD>2.0.CO;2.

[21] K. V. Mackenzie, “Nine-term equation for sound speed in the oceans,” *J. Acoust. Soc. Amer.*, vol. 70, no. 3, pp. 807–812, 1981, doi: 10.1121/1.386919.

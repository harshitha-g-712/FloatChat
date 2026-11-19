# ARGO Data Policy and Open Data Access

## Overview
ARGO is an international program providing free and open access to ocean temperature and salinity profiles globally. Its open data policy is a cornerstone of modern oceanographic research.

## Open Data Principles
- **Free and open**: All ARGO data are freely available without restrictions to anyone worldwide.
- **Real-time delivery**: Profile data are transmitted to data centers within 24 hours of a float surfacing.
- **Quality-controlled**: Data pass both real-time (RT) and delayed-mode (DM) quality control before distribution.
- **No proprietary use**: Individual nations and research groups cannot claim ownership of ARGO data.

## Data Centers and Distribution
Argo data are managed through two **Global Data Assembly Centres (GDACs)**:
1. **Coriolis GDAC** (France) — primary European center
2. **USGODAE GDAC** (USA) — primary American center

Data are also accessible via:
- **Argo ftp/HTTP servers**: Direct profile download in NetCDF format
- **Copernicus Marine Service (CMEMS)**: Aggregated ocean products
- **Euroargo**: European coordination
- **IFREMER**: French oceanographic institution

## Data Types
1. **Real-Time (RT) Data**: Available within 24 hours; preliminary quality control
2. **Delayed Mode (DM) Data**: Available within 1 year; expert-reviewed; more accurate salinity (corrected for sensor drift using climatological references like WOA)

## Quality Control Flags
Every ARGO measurement has a quality flag:
- **1 (Good)**: Passes all checks; reliable for research
- **2 (Probably good)**: Minor anomaly; use with caution
- **3 (Probably bad)**: Fails some checks; not recommended
- **4 (Bad)**: Fails checks; do not use
- **9 (Missing)**: No measurement recorded

ArgoLens filters all displayed data to include only **flag = 1 (Good)** measurements by default.

## Citation Policy
Users of ARGO data should cite:
> Argo (2022). Argo float data and metadata from Global Data Assembly Centre (Argo GDAC). SEANOE. https://doi.org/10.17882/42182

## ArgoLens and ARGO Data
ArgoLens uses a locally ingested SQLite database of real ARGO float profiles from the Bay of Bengal. All data were downloaded from Coriolis GDAC and pass real-time quality control (QC flag = 1). The database covers the period available within the Bay of Bengal ARGO deployment program.

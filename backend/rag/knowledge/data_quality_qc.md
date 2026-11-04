# ARGO Data Quality Control

## Real-Time vs Delayed-Mode QC
ARGO data undergoes two stages of quality control. **Real-time QC** is automated and applied within 24 hours of data receipt: it includes range checks, spike tests, and gradient tests. **Delayed-mode QC** is a manual, expert review performed 6-12 months later, correcting sensor drift (especially salinity) and applying climatological comparisons.

## QC Flag System
Every measurement carries a quality flag:
- **Flag 1**: Good data, passed all tests.
- **Flag 2**: Probably good, but some tests not performed.
- **Flag 3**: Probably bad, failed non-critical tests.
- **Flag 4**: Bad data, failed critical tests or clearly erroneous.
- **Flag 9**: Missing value, no measurement recorded.
Only data with flags 1 or 2 should be used for scientific analysis.

## Common Quality Issues
- **Pressure sensor drift**: Pressure sensors can drift over time; corrected in delayed mode.
- **Salinity sensor biofouling**: Conductivity cells may become contaminated by biological growth, causing salinity to read high. The Owens-Wong method is used for correction.
- **Spikes**: Sudden single-point anomalies, usually electrical noise, detected by comparing adjacent levels.
- **Density inversions**: Physically impossible density decreases with depth, indicating measurement errors.

## FloatChat Data Note
FloatChat stores temperature, salinity, and pressure without the full Argo QC flags. The ingestion process removes clearly invalid values (negative pressure, salinity below 20 PSU), but does not apply the complete flag-based filtering. Results are intended for exploration and education, not peer-reviewed research. Always verify QC handling before using results for scientific publication.

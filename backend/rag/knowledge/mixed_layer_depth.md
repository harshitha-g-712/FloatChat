# Mixed Layer Depth (MLD) in the Bay of Bengal

## Definition
The Mixed Layer Depth (MLD) is the depth of the near-surface layer of the ocean where temperature, salinity, and density are nearly uniform due to wind-driven turbulent mixing and convection.

## Why MLD Matters
- Controls heat exchange between ocean and atmosphere
- Determines nutrient availability for phytoplankton (productivity)
- Affects tropical cyclone intensification (deeper MLD = more heat available = stronger storms)
- Regulates freshwater dilution from river discharge

## MLD Criteria Used
Two standard criteria are commonly used to identify MLD from ARGO profiles:

### 1. Temperature Threshold Criterion (de Boyer Montégut, 2004)
- MLD = depth where temperature drops by **0.2°C** from the surface (10 dbar reference)
- Simple and widely used
- May overestimate MLD in barrier layer regions

### 2. Density Threshold Criterion (Standard)
- MLD = depth where potential density (σθ) increases by **0.03 kg/m³** from the surface
- More physically meaningful in regions with strong salinity gradients
- Recommended for Bay of Bengal due to its fresh surface layer

## Seasonal MLD Variability in Bay of Bengal
- **Pre-monsoon (Apr–May)**: Shallow MLD (~20–40 m); strong stratification due to solar heating
- **Southwest Monsoon (Jun–Sep)**: Deepens to 40–80 m due to wind mixing and freshwater input
- **Post-monsoon (Oct–Nov)**: Shallow again (20–50 m) as winds relax
- **Winter (Dec–Feb)**: 60–100 m; deepest due to surface cooling and convective mixing

## Barrier Layer Thickness (BLT)
The Bay of Bengal exhibits a unique **barrier layer** between:
- **Mixed Layer Base** (defined by temperature)
- **Isothermal Layer Base** (defined by temperature = surface - 0.5°C)

**BLT = Isothermal Layer Depth − Mixed Layer Depth**

A positive BLT indicates a barrier layer where salinity stratification prevents vertical mixing even though temperature is uniform, trapping heat and inhibiting cyclone-induced upwelling of cold water.

## MLD from ARGO Data
ARGO profiles provide temperature and salinity at multiple pressure levels. MLD is computed programmatically by scanning downward from the reference depth (10 dbar) until the threshold criterion is met. The ArgoLens system computes MLD automatically for every dive profile displayed.

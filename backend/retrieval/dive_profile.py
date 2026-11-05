"""Vertical-profile physics for the Sonar & Dive simulator.

Pure functions (no database access) so they can be unit tested.

Method notes (also returned by the API as ``method``):

* Sound speed: Mackenzie (1981), valid for T -2..30 C, S 25..40 PSU, depth 0..8000 m.
  Depth in metres is computed from pressure with Saunders (1981) using the profile latitude.
* Mixed layer depth (MLD): shallowest level where temperature is at least 0.2 C below the
  temperature at ~10 dbar (de Boyer Montegut et al. 2004 criterion), linearly interpolated.
  This is a *temperature-only* MLD. In the Bay of Bengal salinity stratification is strong,
  so it can differ from a density-based MLD.
* Thermocline: depth of the largest |dT/dp| over a window of at least 5 dbar, searched only in
  the upper 500 dbar.
* SOFAR axis: depth of the sound-speed minimum between 300 and 2000 dbar. It is reported only if
  the profile reaches 1000 dbar, has at least 5 sound-speed levels in that window, and the
  minimum is not at the edge of the window. Otherwise it is "not resolved" (None) with a note.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

METHOD = {
    "sound_speed": "Mackenzie (1981)",
    "mixed_layer": "temperature drop of 0.2 C from the ~10 dbar value (temperature-only)",
    "thermocline": "maximum |dT/dp| over >=5 dbar, upper 500 dbar",
    "sofar": "sound-speed minimum, 300-2000 dbar, profile must reach 1000 dbar",
}

MLD_DELTA_T = 0.2
MLD_REF_PRESSURE = 10.0
MLD_REF_MAX_PRESSURE = 30.0      # the reference level must be at most this deep (some floats start at ~25 dbar)
THERMOCLINE_MAX_PRESSURE = 500.0
THERMOCLINE_MIN_SPACING = 5.0
SOFAR_MIN_PROFILE_DEPTH = 1000.0
SOFAR_WINDOW = (300.0, 2000.0)
SOFAR_MIN_LEVELS = 5
SOFAR_BAND_MS = 0.5


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def depth_from_pressure(p_dbar: float, lat_deg: Optional[float] = None) -> float:
    """Depth in metres from pressure in dbar (Saunders 1981 / UNESCO TN 44)."""
    lat = 10.0 if lat_deg is None else float(lat_deg)
    x = math.sin(math.radians(lat)) ** 2
    gravity = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * x) * x) + 1.092e-6 * p_dbar
    num = (((-1.82e-15 * p_dbar + 2.279e-10) * p_dbar - 2.2512e-5) * p_dbar + 9.72659) * p_dbar
    return num / gravity


def sound_speed_mackenzie(t: float, s: float, depth_m: float) -> float:
    """Speed of sound in sea water (m/s), Mackenzie (1981)."""
    return (
        1448.96 + 4.591 * t - 5.304e-2 * t ** 2 + 2.374e-4 * t ** 3
        + 1.340 * (s - 35.0) + 1.630e-2 * depth_m + 1.675e-7 * depth_m ** 2
        - 1.025e-2 * t * (s - 35.0) - 7.139e-13 * t * depth_m ** 3
    )


def potential_density_unesco(t: float, s: float) -> float:
    """Potential density anomaly sigma_theta (kg/m^3) at surface pressure (UNESCO 1983).
    Valid for T -2..40 C, S 0..42 PSU.
    """
    # Pure water density UNESCO 1981
    rhow = (999.842594 + 6.793952e-2 * t - 9.095290e-3 * t ** 2 +
            1.001685e-4 * t ** 3 - 1.120083e-6 * t ** 4 + 6.536332e-9 * t ** 5)
    # Seawater density at p=0
    A = 8.24493e-1 - 4.0899e-3 * t + 7.6438e-5 * t ** 2 - 8.2467e-7 * t ** 3 + 5.3875e-9 * t ** 4
    B = -5.72466e-3 + 1.0227e-4 * t - 1.6546e-6 * t ** 2
    C = 4.8314e-4
    rho = rhow + A * s + B * (s ** 1.5) + C * (s ** 2)
    return round(rho - 1000.0, 3)


MLD_DELTA_SIGMA = 0.03  # de Boyer Montegut (2004) density criterion (kg/m^3)


def _mixed_layer_depth_density(levels: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Density-based mixed layer depth (dbar) where sigma_theta increases by 0.03 kg/m^3
    from the ~10 dbar reference value (de Boyer Montegut et al. 2004).
    """
    valid = [(lv["pressure"], lv["sigma_theta"]) for lv in levels if lv.get("sigma_theta") is not None]
    if len(valid) < 2:
        return None
    ref = min((v for v in valid if v[0] <= MLD_REF_MAX_PRESSURE), key=lambda v: abs(v[0] - MLD_REF_PRESSURE), default=None)
    if ref is None:
        return None
    ref_p, ref_sig = ref
    prev_p, prev_sig = ref_p, ref_sig
    for p, sig in valid:
        if p <= ref_p:
            continue
        if sig - ref_sig >= MLD_DELTA_SIGMA:
            if sig - prev_sig > 0 and prev_p < p:
                frac = (ref_sig + MLD_DELTA_SIGMA - prev_sig) / (sig - prev_sig)
                return round(prev_p + max(0.0, min(1.0, frac)) * (p - prev_p), 1)
            return round(p, 1)
        prev_p, prev_sig = p, sig
    return None


def classify_water_mass(t: Optional[float], s: Optional[float], p: Optional[float] = None) -> str:
    """Identify water mass according to Northern Indian Ocean / Bay of Bengal oceanography."""
    if t is None or s is None:
        return "Unclassified"
    if t >= 27.0 and s < 33.5:
        return "Bay of Bengal Surface Water (BBSW)"
    if t >= 25.0 and s >= 35.0:
        return "Arabian Sea High Salinity Water (ASHSW)"
    if 24.0 <= t < 28.0 and 33.5 <= s <= 34.6:
        return "Equatorial Indian Ocean Surface Water"
    if 10.0 <= t < 20.0 and 34.5 <= s <= 35.2:
        return "Indian Central Water (ICW)"
    if t < 10.0 and p is not None and p >= 800.0:
        return "Indian Deep / Bottom Water"
    return "Transitional / Thermocline Water"


def _mixed_layer_depth(levels: Sequence[Dict[str, Any]]) -> Optional[float]:
    valid = [(lv["pressure"], lv["temperature"]) for lv in levels if lv["temperature"] is not None]
    if len(valid) < 2:
        return None
    ref = min((v for v in valid if v[0] <= MLD_REF_MAX_PRESSURE), key=lambda v: abs(v[0] - MLD_REF_PRESSURE), default=None)
    if ref is None:
        return None            # no measurement near the surface: the reference is unknown
    ref_p, ref_t = ref
    prev_p, prev_t = ref_p, ref_t
    for p, t in valid:
        if p <= ref_p:
            continue
        if ref_t - t >= MLD_DELTA_T:
            if prev_t - t > 0 and prev_p < p:
                frac = (ref_t - MLD_DELTA_T - prev_t) / (t - prev_t)
                return round(prev_p + max(0.0, min(1.0, frac)) * (p - prev_p), 1)
            return round(p, 1)
        prev_p, prev_t = p, t
    return None


def _thermocline(levels: Sequence[Dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    pts = [(lv["pressure"], lv["temperature"]) for lv in levels
           if lv["temperature"] is not None and lv["pressure"] <= THERMOCLINE_MAX_PRESSURE]
    if len(pts) < 3:
        return None, None
    best_grad, best_depth = 0.0, None
    i = 0
    for j in range(len(pts)):
        # latest earlier level that is at least the minimum spacing above level j
        while i + 1 < j and pts[j][0] - pts[i + 1][0] >= THERMOCLINE_MIN_SPACING:
            i += 1
        if j > i and pts[j][0] - pts[i][0] >= THERMOCLINE_MIN_SPACING:
            grad = abs(pts[j][1] - pts[i][1]) / (pts[j][0] - pts[i][0])
            if grad > best_grad:
                best_grad, best_depth = grad, (pts[j][0] + pts[i][0]) / 2.0
    if best_depth is None:
        return None, None
    return round(best_depth, 1), round(best_grad, 4)


def _sofar(levels: Sequence[Dict[str, Any]], max_pressure: float) -> Dict[str, Any]:
    empty = {"depth": None, "speed": None, "band": None}
    if max_pressure < SOFAR_MIN_PROFILE_DEPTH:
        return {**empty, "note": f"Profile only reaches {max_pressure:.0f} dbar; the SOFAR axis needs a profile to at "
                                 f"least {SOFAR_MIN_PROFILE_DEPTH:.0f} dbar."}
    lo, hi = SOFAR_WINDOW
    win = [lv for lv in levels if lv["sound_speed"] is not None and lo <= lv["pressure"] <= hi]
    if len(win) < SOFAR_MIN_LEVELS:
        return {**empty, "note": "Too few temperature/salinity levels between 300 and 2000 dbar to locate the "
                                 "sound-speed minimum."}
    speeds = [lv["sound_speed"] for lv in win]
    # 3-point moving average: the minimum is very flat below ~1000 dbar, so single noisy levels
    # would otherwise decide where the "axis" is.
    smooth = [sum(speeds[max(0, n - 1):n + 2]) / len(speeds[max(0, n - 1):n + 2]) for n in range(len(speeds))]
    k = min(range(len(smooth)), key=lambda n: smooth[n])
    if k == 0 or k == len(win) - 1:
        return {**empty, "note": "No clear sound-speed minimum inside 300-2000 dbar for this profile (not resolved)."}
    near = [win[n]["pressure"] for n in range(len(win)) if smooth[n] <= smooth[k] + SOFAR_BAND_MS]
    return {
        "depth": win[k]["pressure"],
        "speed": round(smooth[k], 1),
        "band": [min(near), max(near)],
        "note": f"Broad, flat minimum: sound speed is within {SOFAR_BAND_MS} m/s of the minimum between "
                f"{min(near):.0f} and {max(near):.0f} dbar, so the axis depth is approximate.",
    }


def build_dive_profile(rows: Sequence[Any], lat: Optional[float] = None) -> Dict[str, Any]:
    """Turn (pressure, temperature, salinity, [temp_qc, sal_qc]) rows into levels plus derived oceanography.

    ``rows`` may be sqlite3.Row objects or tuples; they are sorted by pressure here.
    If temp_qc and sal_qc flags are available, flags 3 (probably bad), 4 (bad), and 9 (missing)
    are treated as NULL to uphold Argo QC scientific standards.
    """
    bad_qc = {3, 4, 9, "3", "4", "9"}
    parsed = []
    for r in rows:
        # Support dict/sqlite3.Row or tuple access
        if hasattr(r, "keys"):
            p = _finite(r["pressure"])
            t = _finite(r["temperature"])
            s = _finite(r["salinity"])
            tq = r["temp_qc"] if "temp_qc" in r.keys() else None
            sq = r["sal_qc"] if "sal_qc" in r.keys() else None
        else:
            p = _finite(r[0])
            t = _finite(r[1]) if len(r) > 1 else None
            s = _finite(r[2]) if len(r) > 2 else None
            tq = r[3] if len(r) > 3 else None
            sq = r[4] if len(r) > 4 else None

        if p is None or p < 0:
            continue
        if tq in bad_qc:
            t = None
        if sq in bad_qc:
            s = None
        parsed.append((p, t, s, tq, sq))
    parsed.sort(key=lambda x: x[0])

    levels: List[Dict[str, Any]] = []
    surface_temp = None
    for p, t, s, tq, sq in parsed:
        speed = None
        sig = None
        water_mass = None
        if t is not None and s is not None:
            speed = round(sound_speed_mackenzie(t, s, depth_from_pressure(p, lat)), 1)
            sig = potential_density_unesco(t, s)
            water_mass = classify_water_mass(t, s, p)
        if t is not None and surface_temp is None:
            surface_temp = t
        levels.append({
            "pressure": round(p, 1),
            "depth": round(p, 1),            # kept for compatibility: plotted on the pressure axis (dbar)
            "temperature": round(t, 2) if t is not None else None,
            "salinity": round(s, 3) if s is not None else None,
            "sound_speed": speed,
            "sigma_theta": sig,
            "water_mass": water_mass,
            "temp_qc": tq,
            "sal_qc": sq,
        })

    max_p = levels[-1]["pressure"] if levels else 0.0
    thermo_depth, thermo_grad = _thermocline(levels)
    sofar = _sofar(levels, max_p)
    mld_t = _mixed_layer_depth(levels)
    mld_rho = _mixed_layer_depth_density(levels)
    blt = round(max(0.0, mld_t - mld_rho), 1) if (mld_t is not None and mld_rho is not None) else None

    return {
        "levels": levels,
        "mixed_layer_depth": mld_t,
        "mixed_layer_depth_density": mld_rho,
        "barrier_layer_thickness": blt,
        "mixed_layer_note": None if mld_t is not None else
            "Not resolved: no level near 10 dbar, or no 0.2 C temperature drop within the profile.",
        "thermocline_depth": thermo_depth,
        "thermocline_gradient": thermo_grad,          # degrees C per dbar
        "sofar_depth": sofar["depth"],                # dbar
        "sofar_speed": sofar["speed"],                # m/s
        "sofar_band": sofar["band"],                  # [top, bottom] dbar within 0.5 m/s of the minimum
        "sofar_note": sofar["note"],
        "surface_temp": round(surface_temp, 2) if surface_temp is not None else None,
        "max_depth": round(max_p, 1),
        "method": METHOD,
    }

"""Calculate OPV E1, E2, E3 losses from EQE, sEQE, and EQE_EL data.

Default inputs match this workspace:
    python calculate_e2.py

The script expects:
    EQE.csv                         wavelength / EQE data
    sEQE.csv                        optional sensitive EQE data
    EQE_EL.csv                      optional EL quantum efficiency vs current density
    normals/solar_irradiation.txt   AM1.5G irradiance, W m^-2 nm^-1
    normals/SQlimit.txt             SQ limit table containing Energy_eV and VOC_V
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.signal import savgol_filter


Q = 1.602176634e-19  # C
H = 6.62607015e-34  # J s
C = 299792458.0  # m s^-1
KB = 1.380649e-23  # J K^-1


class CalculationOptions(Protocol):
    eqe: Path
    seqe: Path
    eqe_el: Path | None
    no_seqe: bool
    solar: Path
    sqlimit: Path
    eg: float | None
    el_current: float | None
    temperature: float
    smooth_window: int
    seqe_switch_nm: float | None
    seqe_switch_fraction: float
    seqe_scale: float | None
    seqe_max_nm: float | None
    seqe_floor: float | None


def read_table(path: Path) -> pd.DataFrame:
    """Read comma-, tab-, or whitespace-delimited numeric tables."""
    header_df = pd.read_csv(path, sep=None, engine="python")
    numeric_rows = header_df.apply(pd.to_numeric, errors="coerce").notna().sum().sum()

    no_header_df = pd.read_csv(path, sep=None, engine="python", header=None)
    no_header_numeric_rows = no_header_df.apply(pd.to_numeric, errors="coerce").notna().sum().sum()

    if no_header_numeric_rows > numeric_rows:
        return no_header_df
    return header_df


def pick_column(df: pd.DataFrame, keywords: tuple[str, ...]) -> str:
    normalized = {str(col).lower().replace(" ", "").replace("_", ""): col for col in df.columns}
    for key in keywords:
        key = key.lower().replace(" ", "").replace("_", "")
        for norm, original in normalized.items():
            if key in norm:
                return original
    raise ValueError(f"Cannot find a column matching {keywords}. Columns are: {list(df.columns)}")


def pick_column_or_position(df: pd.DataFrame, keywords: tuple[str, ...], position: int) -> str:
    try:
        return pick_column(df, keywords)
    except ValueError:
        if len(df.columns) > position:
            return df.columns[position]
        raise ValueError(
            f"Cannot find column {position + 1}; file needs at least {position + 1} columns. "
            f"Columns are: {list(df.columns)}"
        )


def pick_first_numeric_column(df: pd.DataFrame, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for col in df.columns:
        if col in exclude:
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().sum() > 0:
            return col
    raise ValueError(f"Cannot find a numeric column. Columns are: {list(df.columns)}")


def load_eqe(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = read_table(path)
    wavelength_col = pick_column_or_position(df, ("wavelength", "wvlgth", "lambda", "nm"), 0)
    eqe_col = pick_column_or_position(df, ("eqe",), 1)

    wavelength_nm = pd.to_numeric(df[wavelength_col], errors="coerce").to_numpy(float)
    eqe = pd.to_numeric(df[eqe_col], errors="coerce").to_numpy(float)
    mask = np.isfinite(wavelength_nm) & np.isfinite(eqe)
    wavelength_nm = wavelength_nm[mask]
    eqe = eqe[mask]

    if len(wavelength_nm) < 2:
        raise ValueError(f"{path} needs at least two wavelength/EQE data points.")

    if np.nanmax(eqe) > 1.0:
        eqe = eqe / 100.0

    order = np.argsort(wavelength_nm)
    wavelength_nm = wavelength_nm[order]
    eqe = np.clip(eqe[order], 0.0, None)
    return wavelength_nm, eqe


def load_eqe_el(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = read_table(path)
    current_col = pick_column_or_position(df, ("jsc", "current", "ma/cm2", "ma cm-2"), 0)
    try:
        eqe_el_col = pick_column(df, ("eqe_el", "eqeel", "el"))
    except ValueError:
        eqe_el_col = df.columns[1] if len(df.columns) > 1 else pick_first_numeric_column(df, exclude={current_col})

    current_ma_cm2 = pd.to_numeric(df[current_col], errors="coerce").to_numpy(float)
    eqe_el = pd.to_numeric(df[eqe_el_col], errors="coerce").to_numpy(float)
    mask = np.isfinite(current_ma_cm2) & np.isfinite(eqe_el) & (current_ma_cm2 > 0) & (eqe_el > 0)
    current_ma_cm2 = current_ma_cm2[mask]
    eqe_el = eqe_el[mask]

    if len(current_ma_cm2) < 2:
        raise ValueError(f"{path} needs at least two positive current/EQE_EL points for interpolation.")

    eqe_el_header = str(eqe_el_col).lower()
    if "%" in eqe_el_header or np.nanmax(eqe_el) > 1.5:
        eqe_el = eqe_el / 100.0

    order = np.argsort(current_ma_cm2)
    return current_ma_cm2[order], eqe_el[order]


def interpolate_eqe_el(
    current_ma_cm2: np.ndarray,
    eqe_el: np.ndarray,
    target_current_ma_cm2: float,
) -> float:
    if not (current_ma_cm2[0] <= target_current_ma_cm2 <= current_ma_cm2[-1]):
        raise ValueError(
            f"Target current {target_current_ma_cm2:.4g} mA/cm2 is outside EQE_EL range "
            f"{current_ma_cm2[0]:.4g}-{current_ma_cm2[-1]:.4g} mA/cm2."
        )
    # Interpolate log(EQE_EL) versus log(J), which is more stable for current sweeps.
    log_eqe_el = np.interp(
        np.log(target_current_ma_cm2),
        np.log(current_ma_cm2),
        np.log(eqe_el),
    )
    return float(np.exp(log_eqe_el))


def estimate_eg_from_eqe(
    wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    smooth_window: int = 9,
    edge_fraction_max: float = 0.95,
) -> float:
    """Estimate optical gap from the low-energy EQE edge.

    The method converts wavelength to energy and takes the maximum positive
    slope of EQE(E) on the low-energy absorption onset. This is an inflection
    point estimate, useful for automated E2 calculations.
    """
    energy_ev = 1240.0 / wavelength_nm
    order = np.argsort(energy_ev)
    energy_ev = energy_ev[order]
    eqe_e = eqe[order]

    max_eqe = np.nanmax(eqe_e)
    edge_mask = (eqe_e > 0.002 * max_eqe) & (eqe_e < edge_fraction_max * max_eqe)
    if np.count_nonzero(edge_mask) < 5:
        edge_mask = np.ones_like(eqe_e, dtype=bool)

    energy_edge = energy_ev[edge_mask]
    eqe_edge = eqe_e[edge_mask]

    if smooth_window >= len(eqe_edge):
        smooth_window = len(eqe_edge) - 1
    if smooth_window % 2 == 0:
        smooth_window -= 1

    if smooth_window >= 5:
        eqe_smooth = savgol_filter(eqe_edge, smooth_window, polyorder=2)
    else:
        eqe_smooth = eqe_edge

    derivative = np.gradient(eqe_smooth, energy_edge)
    return float(energy_edge[np.argmax(derivative)])


def load_solar_photon_flux(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = read_table(path)
    wavelength_col = pick_column(df, ("wavelength", "wvlgth", "nm"))
    irradiance_col = pick_column(df, ("globaltilt", "irradiance", "w*m-2*nm-1"))

    wavelength_nm = pd.to_numeric(df[wavelength_col], errors="coerce").to_numpy(float)
    irradiance = pd.to_numeric(df[irradiance_col], errors="coerce").to_numpy(float)
    mask = np.isfinite(wavelength_nm) & np.isfinite(irradiance)
    wavelength_nm = wavelength_nm[mask]
    irradiance = irradiance[mask]

    order = np.argsort(wavelength_nm)
    wavelength_nm = wavelength_nm[order]
    irradiance = irradiance[order]

    wavelength_m = wavelength_nm * 1e-9
    photon_energy_j = H * C / wavelength_m
    photon_flux = irradiance / photon_energy_j  # photons m^-2 s^-1 nm^-1
    return wavelength_nm, photon_flux


def blackbody_photon_flux_nm(wavelength_nm: np.ndarray, temperature_k: float) -> np.ndarray:
    wavelength_m = wavelength_nm * 1e-9
    exponent = H * C / (wavelength_m * KB * temperature_k)
    exponent = np.clip(exponent, None, 700.0)
    flux_per_m = 2.0 * np.pi * C / wavelength_m**4 / np.expm1(exponent)
    return flux_per_m * 1e-9  # photons m^-2 s^-1 nm^-1


def integrate_current_density(
    wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    photon_flux_nm: np.ndarray,
) -> float:
    photon_current = np.trapezoid(eqe * photon_flux_nm, wavelength_nm)
    return Q * photon_current  # A m^-2


def interpolate_eqe(
    eqe_wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    target_wavelength_nm: np.ndarray,
) -> np.ndarray:
    interpolator = interp1d(
        eqe_wavelength_nm,
        eqe,
        kind="linear",
        bounds_error=False,
        fill_value=0.0,
    )
    return np.clip(interpolator(target_wavelength_nm), 0.0, None)


def find_seqe_switch_wavelength(
    wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    threshold_fraction: float,
) -> float:
    """Find the red-edge wavelength where ordinary EQE is handed to sEQE."""
    peak_index = int(np.argmax(eqe))
    threshold = threshold_fraction * float(np.max(eqe))
    red_wavelength = wavelength_nm[peak_index:]
    red_eqe = eqe[peak_index:]
    below = np.flatnonzero(red_eqe <= threshold)
    if len(below) == 0:
        return float(wavelength_nm[-1])
    return float(red_wavelength[below[0]])


def scale_seqe_to_eqe(
    eqe_wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    seqe_wavelength_nm: np.ndarray,
    seqe: np.ndarray,
) -> float:
    """Return a robust multiplicative factor that puts sEQE on the EQE scale."""
    normal_on_seqe = interpolate_eqe(eqe_wavelength_nm, eqe, seqe_wavelength_nm)
    max_eqe = float(np.max(eqe))

    overlap = (
        (seqe_wavelength_nm >= eqe_wavelength_nm[0])
        & (seqe_wavelength_nm <= eqe_wavelength_nm[-1])
        & (normal_on_seqe > 0.20 * max_eqe)
        & (seqe > 0)
    )
    if np.count_nonzero(overlap) < 3:
        overlap = (
            (seqe_wavelength_nm >= eqe_wavelength_nm[0])
            & (seqe_wavelength_nm <= eqe_wavelength_nm[-1])
            & (normal_on_seqe > 0.02 * max_eqe)
            & (seqe > 0)
        )

    if np.count_nonzero(overlap) < 3:
        raise ValueError("Not enough overlap between EQE and sEQE to scale sEQE.")

    ratios = normal_on_seqe[overlap] / seqe[overlap]
    ratios = ratios[np.isfinite(ratios) & (ratios > 0)]
    if len(ratios) == 0:
        raise ValueError("Cannot determine a valid EQE/sEQE scale factor.")
    return float(np.median(ratios))


def build_radiative_eqe(
    eqe_wavelength_nm: np.ndarray,
    eqe: np.ndarray,
    seqe_path: Path | None,
    seqe_switch_nm: float | None,
    seqe_switch_fraction: float,
    seqe_scale: float | None,
    seqe_max_nm: float | None,
    seqe_floor: float | None,
) -> tuple[np.ndarray, np.ndarray, dict[str, float | str]]:
    """Combine ordinary EQE and sEQE for the J0,rad integral."""
    eqe_max_nm = float(eqe_wavelength_nm[-1])
    if seqe_path is None or not seqe_path.exists():
        return eqe_wavelength_nm, eqe, {
            "sEQE": "not used",
            "radiative_max_nm": eqe_max_nm,
            "radiative_range_source": "EQE",
        }

    if seqe_max_nm is not None and seqe_max_nm <= eqe_max_nm:
        return eqe_wavelength_nm, eqe, {
            "sEQE": "not used; requested range is within EQE",
            "radiative_max_nm": eqe_max_nm,
            "radiative_range_source": "EQE",
        }

    seqe_wavelength_nm, seqe = load_eqe(seqe_path)
    scale = seqe_scale
    if scale is None:
        scale = scale_seqe_to_eqe(eqe_wavelength_nm, eqe, seqe_wavelength_nm, seqe)
    seqe_scaled = seqe * scale
    if seqe_floor is not None:
        seqe_scaled = np.where(seqe_scaled >= seqe_floor, seqe_scaled, 0.0)

    switch_nm = seqe_switch_nm
    if switch_nm is None:
        switch_nm = find_seqe_switch_wavelength(eqe_wavelength_nm, eqe, seqe_switch_fraction)

    normal_mask = eqe_wavelength_nm < switch_nm
    seqe_mask = seqe_wavelength_nm >= switch_nm
    if seqe_max_nm is not None:
        seqe_mask &= seqe_wavelength_nm <= seqe_max_nm
    if np.count_nonzero(seqe_mask) == 0:
        raise ValueError(f"sEQE has no data at or above switch wavelength {switch_nm:.1f} nm.")

    merged_wavelength_nm = np.concatenate([eqe_wavelength_nm[normal_mask], seqe_wavelength_nm[seqe_mask]])
    merged_eqe = np.concatenate([eqe[normal_mask], seqe_scaled[seqe_mask]])
    order = np.argsort(merged_wavelength_nm)
    return (
        merged_wavelength_nm[order],
        np.clip(merged_eqe[order], 0.0, None),
        {
            "sEQE": str(seqe_path),
            "sEQE_scale": scale,
            "sEQE_switch_nm": switch_nm,
            "sEQE_max_nm": "none" if seqe_max_nm is None else float(seqe_max_nm),
            "sEQE_floor": "none" if seqe_floor is None else float(seqe_floor),
            "radiative_max_nm": float(seqe_max_nm) if seqe_max_nm is not None else float(merged_wavelength_nm[order][-1]),
            "radiative_range_source": "EQE + sEQE",
        },
    )


def lookup_voc_sq(path: Path, eg_ev: float) -> float:
    df = read_table(path)
    energy_col = pick_column(df, ("energy", "ev"))
    voc_col = pick_column(df, ("voc",))

    energy = pd.to_numeric(df[energy_col], errors="coerce").to_numpy(float)
    voc = pd.to_numeric(df[voc_col], errors="coerce").to_numpy(float)
    mask = np.isfinite(energy) & np.isfinite(voc) & (voc > 0)
    energy = energy[mask]
    voc = voc[mask]

    order = np.argsort(energy)
    energy = energy[order]
    voc = voc[order]

    if not (energy[0] <= eg_ev <= energy[-1]):
        raise ValueError(f"Eg={eg_ev:.4f} eV is outside SQ table range {energy[0]:.3f}-{energy[-1]:.3f} eV")
    return float(np.interp(eg_ev, energy, voc))


def calculate(args: CalculationOptions) -> dict[str, float]:
    eqe_wavelength_nm, eqe = load_eqe(args.eqe)
    eg_ev = args.eg if args.eg is not None else estimate_eg_from_eqe(
        eqe_wavelength_nm,
        eqe,
        smooth_window=args.smooth_window,
    )
    seqe_path = None if args.no_seqe else args.seqe
    rad_wavelength_nm, rad_eqe, rad_meta = build_radiative_eqe(
        eqe_wavelength_nm,
        eqe,
        seqe_path,
        args.seqe_switch_nm,
        args.seqe_switch_fraction,
        args.seqe_scale,
        args.seqe_max_nm,
        args.seqe_floor,
    )

    solar_wavelength_nm, solar_photon_flux = load_solar_photon_flux(args.solar)
    eqe_on_solar_grid = interpolate_eqe(eqe_wavelength_nm, eqe, solar_wavelength_nm)
    jsc_rad_a_m2 = integrate_current_density(solar_wavelength_nm, eqe_on_solar_grid, solar_photon_flux)

    bb_photon_flux = blackbody_photon_flux_nm(rad_wavelength_nm, args.temperature)
    j0_rad_a_m2 = integrate_current_density(rad_wavelength_nm, rad_eqe, bb_photon_flux)

    kt_over_q = KB * args.temperature / Q
    voc_rad_v = kt_over_q * np.log(jsc_rad_a_m2 / j0_rad_a_m2 + 1.0)
    voc_sq_v = lookup_voc_sq(args.sqlimit, eg_ev)
    e1_ev = eg_ev - voc_sq_v
    e2_ev = voc_sq_v - voc_rad_v
    e3_ev = np.nan
    eqe_el_at_jsc = np.nan
    e_loss_total_ev = np.nan

    if args.eqe_el is not None and args.eqe_el.exists():
        current_ma_cm2, eqe_el = load_eqe_el(args.eqe_el)
        target_current = args.el_current if args.el_current is not None else jsc_rad_a_m2 * 0.1
        eqe_el_at_jsc = interpolate_eqe_el(current_ma_cm2, eqe_el, target_current)
        e3_ev = -kt_over_q * np.log(eqe_el_at_jsc)
        e_loss_total_ev = e1_ev + e2_ev + e3_ev

    return {
        "Eg_eV": eg_ev,
        "E1_eV": e1_ev,
        "Voc_SQ_V": voc_sq_v,
        "Voc_rad_V": voc_rad_v,
        "E2_eV": e2_ev,
        "EQE_EL_at_Jsc": eqe_el_at_jsc,
        "E3_eV": e3_ev,
        "E_loss_total_eV": e_loss_total_ev,
        "Jsc_rad_mA_cm2": jsc_rad_a_m2 * 0.1,
        "J0_rad_A_m2": j0_rad_a_m2,
        **rad_meta,
    }

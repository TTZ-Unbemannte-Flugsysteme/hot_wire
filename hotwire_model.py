"""Voltage-to-velocity conversion, independent of DAQ hardware and user settings."""

import math
from numbers import Real

import numpy as np


def validate_conversion(coeffs, fluid_temperature):
    """Check the formula's inputs before recording or analysing a measurement."""
    for name in ("a", "b", "e", "m", "Uoffset", "Ts"):
        value = coeffs.get(name)
        if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"Calibration coefficient '{name}' must be a finite number.")
    if not isinstance(fluid_temperature, Real) or isinstance(fluid_temperature, bool) or not math.isfinite(fluid_temperature):
        raise ValueError("Air temperature Tf must be a finite number in degrees Celsius.")
    if coeffs["m"] <= 0 or coeffs["b"] < 0 or coeffs["e"] <= 0:
        raise ValueError("Calibration requires m > 0, b >= 0 and e > 0.")
    if coeffs["Ts"] <= fluid_temperature:
        raise ValueError(f"Sensor temperature Ts ({coeffs['Ts']} C) must be higher than air temperature Tf ({fluid_temperature} C).")


def voltage_to_velocity(u_measured, coeffs, fluid_temperature, *, clip_negative=False):
    """Return velocity [m/s] and U_br^2/(Ts-Tf) for a voltage array or scalar.

    Negative formula bases and non-finite results give NaN. During optimisation,
    clip_negative=True supplies a zero-flow extension so the optimiser can move
    through trial coefficients that would otherwise produce NaN.
    """
    validate_conversion(coeffs, fluid_temperature)
    voltage = np.asarray(u_measured, dtype=float)
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        ratio = (voltage / coeffs["m"] + coeffs["Uoffset"]) ** 2 / (coeffs["Ts"] - fluid_temperature)
        base = coeffs["a"] + coeffs["b"] * ratio
        base = np.maximum(base, 0) if clip_negative else np.where(base >= 0, base, np.nan)
        velocity = base ** coeffs["e"]
    velocity = np.where(np.isfinite(voltage) & np.isfinite(velocity), velocity, np.nan)
    return velocity, ratio

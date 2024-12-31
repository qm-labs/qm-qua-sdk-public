from typing import Tuple

import numpy as np

Correction = Tuple[float, float, float, float]


def convert_to_correction(gain: float, phase: float) -> Correction:
    """
    Convert gain and phase to a correction matrix.
    """
    s = phase
    c = np.polyval([-3.125, 1.5, 1], s**2)
    g_plus = np.polyval([0.5, 1, 1], gain)
    g_minus = np.polyval([0.5, -1, 1], gain)

    c00 = float(g_plus * c)
    c01 = float(g_plus * s)
    c10 = float(g_minus * s)
    c11 = float(g_minus * c)

    return c00, c01, c10, c11

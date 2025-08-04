def format_float(f: float) -> str:
    return "{:.3f}".format(f)


def pretty_string_freq(f: float) -> str:
    if f < 1000:
        div, units = 1.0, "Hz"
    elif 1000 <= f < 1_000_000:
        div, units = 1000.0, "kHz"
    else:
        div, units = 1e6, "MHz"
    return f"{format_float(f / div).rstrip('0').rstrip('.')}{units}"

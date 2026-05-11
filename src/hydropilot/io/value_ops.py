from typing import Optional, Tuple


def apply_param_mode(original_val: float, input_val: float, *, mode: int, typ: int):
    if mode == 0:
        raw = original_val * (1.0 + float(input_val))
    elif mode == 1:
        raw = float(input_val)
    elif mode == 2:
        raw = original_val + float(input_val)
    else:
        raw = float(input_val)

    if typ == 1:
        return int(raw)
    return raw


def clamp_value(value, *, lb: Optional[float], ub: Optional[float]) -> Tuple[float, bool]:
    clamped = value
    if lb is not None and clamped < lb:
        clamped = lb
    if ub is not None and clamped > ub:
        clamped = ub
    return clamped, clamped != value

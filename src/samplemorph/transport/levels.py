from __future__ import annotations


def level_path(first: float, second: float, *, weight: float, exponent: float) -> float:
    """The energy a point between two frames carries: the power mean of theirs at `exponent`.

    At a third, the loudness domain, the path moves evenly in how loud it is heard, returns each end
    exactly, and stays between the two, so a frame meeting silence arrives at the midpoint half as loud.
    """
    mean = (1.0 - weight) * first**exponent + weight * second**exponent
    return float(mean ** (1.0 / exponent))

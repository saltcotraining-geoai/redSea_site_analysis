"""Multi-criteria scoring for the Sudan site analysis (pure Python, no QGIS).

Kept separate from PyQGIS so it can be tested and explained on its own.
QGIS has no rank() expression, so percentile ranks are computed here.
"""
import math


def _rank_pct(values):
    """Average-rank percentile in 0..1 (ties share a rank). One value -> 1."""
    n = len(values)
    if n == 1:
        return [1.0]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2                      # 0-based average rank of the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg / (n - 1)
        i = j + 1
    return ranks


def _minmax(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def normalise(values, method="rank", higher_is_better=True):
    """values -> 0..1 where 1 is always the best. Missing values (None) get 0 (worst)."""
    have = [i for i, v in enumerate(values) if v is not None]
    out = [0.0] * len(values)
    if not have:
        return out
    v = [float(values[i]) for i in have]
    if method == "log_minmax":
        v = [math.log1p(max(x, 0.0)) for x in v]
        n = _minmax(v)
    elif method == "minmax":
        n = _minmax(v)
    elif method == "rank":
        n = _rank_pct(v)
    else:
        raise ValueError(f"unknown normalisation '{method}' (use rank, minmax or log_minmax)")
    if len(set(v)) == 1:
        # one site, or all sites equal: the factor cannot tell them apart, so every
        # site gets full marks whichever direction is "better" (flipping 1 -> 0 for
        # lower-is-better factors would silently drop their weight from the score)
        n = [1.0] * len(v)
    elif not higher_is_better:
        n = [1.0 - x for x in n]
    for i, x in zip(have, n):
        out[i] = x
    return out


def effective_weights(factors, scenario=None):
    """Enabled factors only, weights rescaled to sum to 1.

    scenario: optional {factor: weight}; enabled factors it does not name get 0,
    and factors it names that are switched off are ignored.
    """
    enabled = {k: f for k, f in factors.items() if f.get("enabled")}
    raw = {k: (scenario.get(k, 0.0) if isinstance(scenario, dict) else f["weight"]) for k, f in enabled.items()}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("all enabled factors have weight 0")
    return {k: w / total for k, w in raw.items() if w > 0}


def score(rows, factors, weights, method="rank"):
    """rows: list of dicts with the factor fields. Returns (scores, {factor: normalised list})."""
    norms = {}
    for k in weights:
        f = factors[k]
        norms[k] = normalise([r.get(f["field"]) for r in rows], method, f["higher_is_better"])
    scores = [sum(weights[k] * norms[k][i] for k in weights) for i in range(len(rows))]
    return scores, norms


def ranks(scores, tiebreak):
    """1 = best. Ties broken by tiebreak (e.g. site_id, lower first)."""
    # round first: summing the same weights in a different order can differ in the
    # last bit, which would make exact ties rank differently in Python and JS
    order = sorted(range(len(scores)), key=lambda i: (-round(scores[i], 9), tiebreak[i]))
    out = [0] * len(scores)
    for r, i in enumerate(order, start=1):
        out[i] = r
    return out

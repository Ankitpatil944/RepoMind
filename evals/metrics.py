"""Pure metric functions (no DB, no models) so they are unit-testable."""

import math


def first_relevant_rank(retrieved: list[str], relevant: set[str]) -> int | None:
    """1-indexed rank of the first relevant item, or None."""
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return rank
    return None


def hit_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if relevant & set(retrieved[:k]) else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(relevant & set(retrieved[:k])) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    rank = first_relevant_rank(retrieved, relevant)
    return 1.0 / rank if rank else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile, p in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(math.ceil(p / 100 * len(ordered)) - 1, 0)
    return ordered[index]


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


_FLAGS = ("handles_authentication", "requires_auth")


def score_endpoints(expected: list[dict], found: list[dict]) -> dict:
    """Compare detected endpoints with labelled ones.

    Detection is by (METHOD, path). Classification flags are scored only on
    endpoints that were both labelled and detected."""
    exp = {(e["method"].upper(), e["path"]): e for e in expected}
    got = {(f["method"].upper(), f["path"]): f for f in found}
    matched = sorted(set(exp) & set(got))

    detection = prf(len(matched), len(set(got) - set(exp)), len(set(exp) - set(got)))
    out: dict = {
        "detection": detection,
        "missing": [f"{m} {p}" for m, p in sorted(set(exp) - set(got))],
        "spurious": [f"{m} {p}" for m, p in sorted(set(got) - set(exp))],
        "mismatches": [],
    }

    all_correct = 0
    for flag in _FLAGS:
        tp = fp = fn = 0
        for key in matched:
            want, have = bool(exp[key][flag]), bool(got[key][flag])
            tp += want and have
            fp += have and not want
            fn += want and not have
            if want != have:
                out["mismatches"].append(
                    {
                        "route": f"{key[0]} {key[1]}",
                        "field": flag,
                        "expected": want,
                        "got": have,
                        "evidence": got[key].get("evidence", []),
                        "note": exp[key].get("note"),
                    }
                )
        out[flag] = prf(tp, fp, fn)

    for key in matched:
        if all(bool(exp[key][f]) == bool(got[key][f]) for f in _FLAGS):
            all_correct += 1
    out["classification_accuracy"] = all_correct / len(matched) if matched else 0.0
    return out

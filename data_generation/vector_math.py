from __future__ import annotations


def weighted_average(vectors: list[tuple[list[float], float]]) -> list[float]:
    valid = [(vector, weight) for vector, weight in vectors if vector and weight > 0]
    if not valid:
        return []

    dimension = len(valid[0][0])
    totals = [0.0] * dimension
    total_weight = 0.0

    for vector, weight in valid:
        if len(vector) != dimension:
            continue
        total_weight += weight
        for index, value in enumerate(vector):
            totals[index] += value * weight

    if total_weight <= 0:
        return []
    return [value / total_weight for value in totals]

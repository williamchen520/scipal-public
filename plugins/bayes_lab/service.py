"""Small GP-UCB study for optional offline parameter search.

No core imports. The plugin is disabled by default; this module only proposes
points and records observations supplied by the caller.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

import numpy as np


def _rbf(a: np.ndarray, b: np.ndarray, length: float = 0.3) -> np.ndarray:
    diff = a[:, None, :] - b[None, :, :]
    return np.exp(-np.sum(diff * diff, axis=2) / (2 * length * length))


class BayesianStudy:
    def __init__(self, bounds: list[tuple[float, float]], *, kappa: float = 2.0, seed: int = 42):
        if not bounds:
            raise ValueError("bounds must not be empty")
        self.bounds = [(float(low), float(high)) for low, high in bounds]
        if any(high <= low for low, high in self.bounds):
            raise ValueError("each bound must have high > low")
        self.kappa = float(kappa)
        self.rng = random.Random(seed)
        self.observations: list[tuple[list[float], float]] = []

    def _norm(self, point: list[float]) -> np.ndarray:
        return np.array([
            (float(value) - low) / (high - low)
            for value, (low, high) in zip(point, self.bounds)
        ], dtype=float)

    def _denorm(self, point: np.ndarray) -> list[float]:
        return [
            round(low + float(value) * (high - low), 6)
            for value, (low, high) in zip(point, self.bounds)
        ]

    def observe(self, point: list[float], value: float) -> None:
        if len(point) != len(self.bounds):
            raise ValueError("point dimension mismatch")
        for value_i, (low, high) in zip(point, self.bounds):
            if not low <= float(value_i) <= high:
                raise ValueError("point outside bounds")
        self.observations.append(([float(item) for item in point], float(value)))

    def suggest(self, *, candidates: int = 256) -> list[float]:
        if not self.observations:
            return [round(self.rng.uniform(low, high), 6) for low, high in self.bounds]
        x = np.array([self._norm(point) for point, _ in self.observations])
        y = np.array([value for _, value in self.observations], dtype=float)
        mean_y, std_y = float(y.mean()), float(y.std() or 1.0)
        y_norm = (y - mean_y) / std_y
        noise = 1e-4
        kernel = _rbf(x, x) + noise * np.eye(len(x))
        try:
            chol = np.linalg.cholesky(kernel)
            alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, y_norm))
        except np.linalg.LinAlgError:
            return self._denorm(np.array([
                self.rng.random() for _ in self.bounds
            ]))
        pool = np.array([
            [self.rng.random() for _ in self.bounds]
            for _ in range(max(16, min(candidates, 4096)))
        ])
        k_star = _rbf(pool, x)
        mean = k_star @ alpha
        v = np.linalg.solve(chol, k_star.T)
        variance = np.maximum(0.0, 1.0 - np.sum(v * v, axis=0))
        ucb = mean + self.kappa * np.sqrt(variance)
        return self._denorm(pool[int(np.argmax(ucb))])

    def as_dict(self) -> dict[str, Any]:
        return {
            "study_id": f"bo_{uuid.uuid4().hex[:12]}",
            "bounds": self.bounds,
            "observations": [
                {"point": point, "value": value}
                for point, value in self.observations
            ],
        }

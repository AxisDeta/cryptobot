from __future__ import annotations

import math
from typing import Iterable


def _sigmoid(x: float) -> float:
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class DirectionModel:
    """Ensembled direction model: scaled logistic + distance-weighted kNN."""

    def __init__(self, lr: float = 0.08, epochs: int = 180, knn_k: int = 21) -> None:
        self.lr = lr
        self.epochs = epochs
        self.requested_knn_k = knn_k

        self.weights: list[float] = []
        self.bias: float = 0.0
        self.feature_means: list[float] = []
        self.feature_stds: list[float] = []

        self.train_X_scaled: list[list[float]] = []
        self.train_y: list[int] = []
        self.knn_k: int = 0

        self.logistic_weight: float = 0.7
        self.metrics: dict[str, float] = {}

    def fit(self, X: list[list[float]], y: list[int]) -> None:
        if not X:
            raise ValueError("X cannot be empty")
        if len(X) != len(y):
            raise ValueError("X and y length mismatch")

        targets = [1 if v > 0 else 0 for v in y]
        self._fit_scaler(X)
        Xs = [self._scale_row(row) for row in X]

        self.weights, self.bias = self._fit_logistic_params(Xs, targets)
        self.train_X_scaled = Xs
        self.train_y = targets

        base_k = max(3, int(len(Xs) ** 0.5))
        if base_k % 2 == 0:
            base_k += 1
        self.knn_k = max(3, min(self.requested_knn_k, base_k, len(Xs)))

        self._calibrate_ensemble(Xs, targets)

    def predict_proba(self, row: list[float]) -> float:
        if not self.weights:
            raise ValueError("Model is not trained")
        scaled = self._scale_row(row)
        p_log = _sigmoid(self._linear(scaled))
        p_knn = self._predict_knn_scaled(scaled)
        mixed = (self.logistic_weight * p_log) + ((1.0 - self.logistic_weight) * p_knn)
        return _clamp(mixed)

    def _fit_scaler(self, X: list[list[float]]) -> None:
        n_features = len(X[0])
        n = float(len(X))
        means = [0.0] * n_features
        for row in X:
            for i, val in enumerate(row):
                means[i] += float(val)
        means = [m / n for m in means]

        stds = [0.0] * n_features
        for row in X:
            for i, val in enumerate(row):
                diff = float(val) - means[i]
                stds[i] += diff * diff
        stds = [max((s / n) ** 0.5, 1e-9) for s in stds]

        self.feature_means = means
        self.feature_stds = stds

    def _scale_row(self, row: list[float]) -> list[float]:
        return [
            (float(v) - self.feature_means[i]) / self.feature_stds[i]
            for i, v in enumerate(row)
        ]

    def _fit_logistic_params(self, Xs: list[list[float]], y: list[int]) -> tuple[list[float], float]:
        n_features = len(Xs[0])
        w = [0.0] * n_features
        b = 0.0
        n = float(len(Xs))

        for _ in range(self.epochs):
            grad_w = [0.0] * n_features
            grad_b = 0.0
            for row, t in zip(Xs, y):
                z = sum(ww * x for ww, x in zip(w, row)) + b
                pred = _sigmoid(z)
                err = pred - t
                for i, x in enumerate(row):
                    grad_w[i] += err * x
                grad_b += err

            l2 = 1e-4
            for i in range(n_features):
                grad_w[i] = (grad_w[i] / n) + (l2 * w[i])
                w[i] -= self.lr * grad_w[i]
            b -= self.lr * (grad_b / n)

        return w, b

    def _linear(self, scaled_row: list[float]) -> float:
        return sum(w * x for w, x in zip(self.weights, scaled_row)) + self.bias

    @staticmethod
    def _brier(y_true: Iterable[int], y_prob: Iterable[float]) -> float:
        yt = list(y_true)
        yp = list(y_prob)
        if not yt:
            return 0.0
        return sum((float(p) - float(t)) ** 2 for t, p in zip(yt, yp)) / float(len(yt))

    @staticmethod
    def _accuracy(y_true: Iterable[int], y_prob: Iterable[float]) -> float:
        yt = list(y_true)
        yp = list(y_prob)
        if not yt:
            return 0.0
        hits = 0
        for t, p in zip(yt, yp):
            pred = 1 if float(p) >= 0.5 else 0
            if pred == int(t):
                hits += 1
        return hits / float(len(yt))

    def _predict_knn_scaled(self, scaled_row: list[float], train_rows: list[list[float]] | None = None, train_targets: list[int] | None = None) -> float:
        rows = train_rows if train_rows is not None else self.train_X_scaled
        targets = train_targets if train_targets is not None else self.train_y
        if not rows:
            return 0.5

        k = min(self.knn_k if self.knn_k else self.requested_knn_k, len(rows))
        dists: list[tuple[float, int]] = []
        for r, t in zip(rows, targets):
            d2 = 0.0
            for a, b in zip(r, scaled_row):
                diff = a - b
                d2 += diff * diff
            dists.append((d2, t))
        dists.sort(key=lambda x: x[0])

        eps = 1e-9
        top = dists[:k]
        weighted_pos = 0.0
        weight_sum = 0.0
        for d2, t in top:
            w = 1.0 / (math.sqrt(d2) + eps)
            weighted_pos += w * float(t)
            weight_sum += w
        return (weighted_pos / weight_sum) if weight_sum else 0.5

    def _calibrate_ensemble(self, Xs: list[list[float]], y: list[int]) -> None:
        n = len(Xs)
        if n < 40:
            probs = [
                (self.logistic_weight * _sigmoid(sum(w * x for w, x in zip(self.weights, row)) + self.bias))
                + ((1.0 - self.logistic_weight) * self._predict_knn_scaled(row))
                for row in Xs
            ]
            self.metrics = {
                "accuracy": round(self._accuracy(y, probs), 6),
                "brier": round(self._brier(y, probs), 6),
                "samples": float(n),
                "validation_samples": 0.0,
                "model_blend_logistic": round(self.logistic_weight, 6),
            }
            return

        split = max(25, int(n * 0.7))
        split = min(split, n - 10)

        X_train = Xs[:split]
        y_train = y[:split]
        X_val = Xs[split:]
        y_val = y[split:]

        if not X_train or not X_val:
            return

        temp_w, temp_b = self._fit_logistic_params(X_train, y_train)

        def p_log(row: list[float]) -> float:
            return _sigmoid(sum(w * x for w, x in zip(temp_w, row)) + temp_b)

        weights = [0.2, 0.35, 0.5, 0.65, 0.8]
        best_w = self.logistic_weight
        best_brier = float("inf")
        best_probs: list[float] = []

        for mix in weights:
            probs = []
            for row in X_val:
                pl = p_log(row)
                pk = self._predict_knn_scaled(row, train_rows=X_train, train_targets=y_train)
                probs.append(_clamp((mix * pl) + ((1.0 - mix) * pk)))
            brier = self._brier(y_val, probs)
            if brier < best_brier:
                best_brier = brier
                best_w = mix
                best_probs = probs

        self.logistic_weight = best_w
        self.metrics = {
            "accuracy": round(self._accuracy(y_val, best_probs), 6),
            "brier": round(best_brier, 6),
            "samples": float(n),
            "validation_samples": float(len(y_val)),
            "model_blend_logistic": round(self.logistic_weight, 6),
        }


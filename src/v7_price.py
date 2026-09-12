"""Causal seasonal and ridge price forecasts from observed history."""
from pathlib import Path
import argparse
import json
import numpy as np
from src.q12 import ridge_fit
from src.q34_data import read_extended


def features_at(flat, origin):
    target = np.arange(origin, origin + 144)
    assert (target - 144 < origin).all() and origin >= 1008
    hour = (target % 144 + .5) / 144
    dow = (target // 144 + 2) % 7
    return np.column_stack([flat[target-144], flat[target-1008],
        np.sin(2*np.pi*hour), np.cos(2*np.pi*hour),
        np.sin(2*np.pi*dow/7), np.cos(2*np.pi*dow/7)]).astype('float32')


def ridge_features(x):
    a, b = x[..., 0], x[..., 1]
    context = np.stack([a.mean(-1), b.mean(-1), a.std(-1), b.std(-1)], axis=-1)
    context = np.broadcast_to(context[..., None, :], (*a.shape, 4))
    return np.concatenate([x, np.stack([a-b, a*b], axis=-1), context], axis=-1)


def reconstruct(data):
    flat = data['actual_price'].ravel()
    result = {k: np.full((365, 4, 144), np.nan) for k in ['seasonal', 'ridge']}
    for day in range(7, 365):
        for version in range(4):
            result['seasonal'][day, version] = features_at(flat, day*144+version*36)[:, :2].mean(-1)
    fits = [d for d in range(14, 365) if d in [14, 21] or data['dates'][d].day == 1]
    origins = np.arange(1008, len(flat)-143, 36)
    for i, day in enumerate(fits):
        end = fits[i+1] if i+1 < len(fits) else 365
        oo = origins[(origins+144 <= day*144) & (origins >= max(1008, day*144-60*144))]
        x = np.stack([features_at(flat, o) for o in oo])
        y = np.stack([flat[o:o+144] for o in oo]).astype('float32')
        mean, scale, coef, intercept = ridge_fit(ridge_features(x).reshape(-1, 12), y.ravel(), 1.)
        future = np.stack([features_at(flat, d*144+v*36) for d in range(day, end) for v in range(4)])
        values = ((ridge_features(future)-mean)/scale) @ coef + intercept
        result['ridge'][day:end] = np.maximum(values.reshape(end-day, 4, 144), .001)
    result['ridge'][7:14] = result['seasonal'][7:14]
    return result, fits


def residual_bands(actual, predictions, version=0):
    """Historical 10%-90% residual ranges, not guaranteed coverage intervals."""
    lower = np.full_like(actual, np.nan); upper = lower.copy()
    start = version*36
    for day in range(31, 365):
        left = max(7, day-28)
        residual = actual[left:day, start:] - predictions[left:day, version, :144-start]
        q = np.quantile(residual, [.1, .9], axis=0)
        point = predictions[day, version, :144-start]
        lower[day, start:] = np.maximum(.001, point + q[0])
        upper[day, start:] = np.maximum(.001, point + q[1])
    return lower, upper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--out', type=Path, default=Path('artifacts/v7'))
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    data, _ = read_extended(args.data_root); result, fits = reconstruct(data)
    prior = np.load('artifacts/q34/price_forecasts.npz')
    errors = {}
    for key in result:
        errors[key] = float(np.max(np.abs(result[key][14:] - prior[key][14:])))
        np.testing.assert_allclose(result[key][14:], prior[key][14:], atol=1e-10, rtol=0)
    np.savez_compressed(args.out/'price_forecasts.npz', **result)
    audit = dict(status='PASS', ridge_refits=len(fits), max_cache_difference=errors,
        information='All feature prices and training targets precede issue time',
        models=['seasonal', 'ridge'], alpha=1., training_days=60)
    (args.out/'price_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    main()

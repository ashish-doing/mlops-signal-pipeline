# MLOps Batch Signal Pipeline

![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat-square&logo=python)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker)
![Status](https://img.shields.io/badge/status-success-brightgreen?style=flat-square)
![Seed](https://img.shields.io/badge/seed-42-orange?style=flat-square)

A minimal, reproducible MLOps-style batch job that loads real OHLCV market data, computes a rolling-mean trading signal, and emits structured metrics — runnable locally or inside Docker in one command.

---

## What it does

```
data.csv (10,000 rows OHLCV)
    │
    ▼
┌─────────────────────────────────────────────────┐
│                   run.py                        │
│                                                 │
│  1. Load + validate config.yaml                 │
│  2. Load + validate data.csv                    │
│  3. Rolling mean on close (window=5)            │
│  4. Binary signal: 1 if close > mean, else 0   │
│  5. Compute metrics + latency                   │
└─────────────────────────────────────────────────┘
    │                    │
    ▼                    ▼
metrics.json           run.log
(machine-readable)   (human-readable)
```

**Signal logic:**
- `signal = 1` → close price is **above** the rolling mean (bullish)
- `signal = 0` → close price is **at or below** the rolling mean (bearish)
- First `window-1` rows produce NaN and are excluded from signal computation

---

## Results (sample run)

| Metric | Value |
|--------|-------|
| Rows processed | 10,000 |
| Signal rate | 0.4991 (49.91% bullish) |
| Bullish signals | 4,989 |
| Bearish signals | 5,007 |
| Latency | 19ms |
| Seed | 42 |
| Status | success |

---

## Project structure

```
.
├── run.py            # Main pipeline
├── config.yaml       # Seed, window, version
├── data.csv          # 10,000-row OHLCV dataset (BTC/USD, 1-min)
├── requirements.txt
├── Dockerfile
├── metrics.json      # Sample output (successful run)
├── run.log           # Sample log (successful run)
└── README.md
```

---

## Quickstart

### Local run

**Prerequisites:** Python 3.9+, pip

```bash
pip install -r requirements.txt

python run.py \
  --input    data.csv \
  --config   config.yaml \
  --output   metrics.json \
  --log-file run.log
```

**Outputs:**
- `metrics.json` — structured metrics (machine-readable)
- `run.log` — detailed execution log (human-readable)
- Final JSON printed to stdout

### Docker (one command)

```bash
docker build -t mlops-task .
docker run --rm mlops-task
```

The container bundles `data.csv` and `config.yaml`, runs the full pipeline, and prints the final JSON to stdout.

To retrieve output files from the container:

```bash
docker run --rm -v $(pwd)/output:/app mlops-task
# metrics.json and run.log will appear in ./output/
```

Exit code `0` = success, non-zero = failure.

---

## Configuration (`config.yaml`)

```yaml
seed: 42
window: 5
version: "v1"
```

| Key | Type | Description |
|-----|------|-------------|
| `seed` | int | NumPy random seed — guarantees reproducibility |
| `window` | int | Rolling mean window size |
| `version` | string | Pipeline version tag (appears in metrics.json) |

---

## Output format

### metrics.json — success

```json
{
  "version": "v1",
  "rows_processed": 10000,
  "metric": "signal_rate",
  "value": 0.4991,
  "latency_ms": 19,
  "seed": 42,
  "status": "success"
}
```

### metrics.json — error

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found. Columns present: ['open', 'high']"
}
```

> Metrics file is always written — even on failure. This ensures monitoring systems always have a parseable output.

### run.log (sample)

```
2026-04-21T12:09:56 [INFO] === Job start ===
2026-04-21T12:09:56 [INFO] Config loaded — seed=42  window=5  version=v1
2026-04-21T12:09:56 [INFO] NumPy random seed set to 42
2026-04-21T12:09:56 [INFO] Dataset loaded — 10000 rows, columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume_btc', 'volume_usd']
2026-04-21T12:09:56 [INFO] Computing rolling mean on 'close' (window=5)
2026-04-21T12:09:56 [INFO] Rolling mean computed (window=5) — 4 leading NaN rows excluded from signal
2026-04-21T12:09:56 [INFO] Generating binary signal...
2026-04-21T12:09:56 [INFO] Signal generated — 9996 valid rows  |  signal_rate=0.4991  (1s: 4989  0s: 5007)
2026-04-21T12:09:56 [INFO] Metrics — rows_processed=10000  signal_rate=0.4991  latency_ms=19
2026-04-21T12:09:56 [INFO] === Job complete — status: success ===
```

---

## Validation & error handling

The pipeline handles all failure cases and always writes `metrics.json`:

| Case | Behaviour |
|------|-----------|
| Missing input file | Caught, error written to metrics.json, exit 1 |
| Invalid CSV format | Caught, error written to metrics.json, exit 1 |
| Empty file | Caught, error written to metrics.json, exit 1 |
| Missing `close` column | Caught, error written to metrics.json, exit 1 |
| Invalid config structure | Caught, error written to metrics.json, exit 1 |

---

## Design principles

**Reproducibility** — every parameter lives in `config.yaml`. Seed is set before any processing. Same config + same data = identical output every run.

**Observability** — structured `metrics.json` for dashboards, detailed timestamped `run.log` for debugging. Logs cover every step from start to finish.

**Deployment readiness** — fully Dockerized with `python:3.9-slim`. No hardcoded paths. One-command build and run. Exit codes signal success/failure to orchestrators.
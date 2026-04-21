# MLOps Batch Signal Pipeline

A minimal, reproducible MLOps-style batch job that loads OHLCV data, computes a rolling-mean signal, and emits structured metrics — runnable locally or inside Docker.

---

## Project structure

```
.
├── run.py            # Main pipeline
├── config.yaml       # Seed, window, version
├── data.csv          # 10 000-row OHLCV dataset
├── requirements.txt
├── Dockerfile
├── metrics.json      # Sample output (successful run)
├── run.log           # Sample log (successful run)
└── README.md
```

---

## Local run

### Prerequisites

- Python 3.9+
- pip

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python run.py \
  --input    data.csv \
  --config   config.yaml \
  --output   metrics.json \
  --log-file run.log
```

Outputs:
- `metrics.json` — structured metrics
- `run.log` — detailed execution log
- Final JSON also printed to stdout

---

## Docker

### Build

```bash
docker build -t mlops-task .
```

### Run

```bash
docker run --rm mlops-task
```

The container bundles `data.csv` and `config.yaml`, runs the pipeline, writes `metrics.json` + `run.log` inside the container, and prints the final JSON to stdout.

To retrieve output files from the container:

```bash
docker run --rm -v $(pwd)/output:/app mlops-task
# metrics.json and run.log will appear in ./output/
```

Exit code `0` = success, non-zero = failure.

---

## Configuration (`config.yaml`)

| Key       | Type    | Description                        |
|-----------|---------|------------------------------------|
| `seed`    | int     | NumPy random seed (reproducibility)|
| `window`  | int     | Rolling mean window size           |
| `version` | string  | Pipeline version tag               |

---

## Example `metrics.json`

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

### Error output

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found. Columns present: ['open', 'high']"
}
```

---

## Signal logic

1. **Rolling mean** — computed over `close` with the configured `window`. The first `window-1` rows produce NaN and are excluded from signal computation.
2. **Signal** — `1` if `close > rolling_mean`, else `0`.
3. **signal_rate** — mean of valid signal values.

Results are fully deterministic: same config + same data → same metrics every run.
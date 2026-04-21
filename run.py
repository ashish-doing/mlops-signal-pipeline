"""
MLOps-style batch signal pipeline.
Usage: python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("mlops_pipeline")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    # File handler
    fh = logging.FileHandler(log_file, mode="w")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Stream handler (stdout)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def write_metrics(output_path: str, payload: dict) -> None:
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)


def load_config(config_path: str, logger: logging.Logger) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("Config YAML must be a mapping at the top level.")
    required = {"seed", "window", "version"}
    missing = required - cfg.keys()
    if missing:
        raise KeyError(f"Config missing required fields: {missing}")
    if not isinstance(cfg["seed"], int):
        raise TypeError(f"'seed' must be an integer, got {type(cfg['seed']).__name__}")
    if not isinstance(cfg["window"], int) or cfg["window"] < 1:
        raise ValueError(f"'window' must be a positive integer, got {cfg['window']}")
    if not isinstance(cfg["version"], str):
        raise TypeError(f"'version' must be a string, got {type(cfg['version']).__name__}")
    logger.info(
        "Config loaded — seed=%d  window=%d  version=%s",
        cfg["seed"], cfg["window"], cfg["version"],
    )
    return cfg


def load_dataset(input_path: str, logger: logging.Logger) -> pd.DataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc
    if df.empty:
        raise ValueError("Input CSV is empty.")
    if "close" not in df.columns:
        raise KeyError(
            f"Required column 'close' not found. Columns present: {list(df.columns)}"
        )
    logger.info("Dataset loaded — %d rows, columns: %s", len(df), list(df.columns))
    return df


def compute_rolling_mean(series: pd.Series, window: int, logger: logging.Logger) -> pd.Series:
    """
    Compute rolling mean. The first (window-1) rows will be NaN;
    those rows are excluded from signal computation.
    """
    rolled = series.rolling(window=window, min_periods=window).mean()
    nan_count = rolled.isna().sum()
    logger.info(
        "Rolling mean computed (window=%d) — %d leading NaN rows excluded from signal",
        window, nan_count,
    )
    return rolled


def compute_signal(close: pd.Series, rolling_mean: pd.Series, logger: logging.Logger) -> pd.Series:
    """signal = 1 if close > rolling_mean, else 0. Rows where rolling_mean is NaN are excluded."""
    valid = rolling_mean.notna()
    signal = pd.Series(np.nan, index=close.index)
    signal[valid] = (close[valid] > rolling_mean[valid]).astype(int)
    valid_signals = signal[valid]
    logger.info(
        "Signal generated — %d valid rows  |  signal_rate=%.4f  (1s: %d  0s: %d)",
        len(valid_signals),
        valid_signals.mean(),
        valid_signals.sum(),
        (valid_signals == 0).sum(),
    )
    return valid_signals


def main():
    parser = argparse.ArgumentParser(description="MLOps batch signal pipeline")
    parser.add_argument("--input",    required=True, help="Path to input CSV")
    parser.add_argument("--config",   required=True, help="Path to YAML config")
    parser.add_argument("--output",   required=True, help="Path for output metrics JSON")
    parser.add_argument("--log-file", required=True, dest="log_file", help="Path for log file")
    args = parser.parse_args()

    logger = setup_logging(args.log_file)
    start_time = time.time()
    logger.info("=== Job start ===")

    version = "unknown"

    try:
        # 1. Load + validate config
        cfg = load_config(args.config, logger)
        version = cfg["version"]

        # 2. Set seed for reproducibility
        np.random.seed(cfg["seed"])
        logger.info("NumPy random seed set to %d", cfg["seed"])

        # 3. Load + validate dataset
        df = load_dataset(args.input, logger)

        # 4. Rolling mean
        logger.info("Computing rolling mean on 'close' (window=%d)…", cfg["window"])
        rolling_mean = compute_rolling_mean(df["close"], cfg["window"], logger)

        # 5. Signal generation
        logger.info("Generating binary signal…")
        signal = compute_signal(df["close"], rolling_mean, logger)

        # 6. Metrics
        rows_processed = len(df)
        signal_rate = round(float(signal.mean()), 4)
        latency_ms = int((time.time() - start_time) * 1000)

        metrics = {
            "version": version,
            "rows_processed": rows_processed,
            "metric": "signal_rate",
            "value": signal_rate,
            "latency_ms": latency_ms,
            "seed": cfg["seed"],
            "status": "success",
        }
        write_metrics(args.output, metrics)

        logger.info(
            "Metrics — rows_processed=%d  signal_rate=%.4f  latency_ms=%d",
            rows_processed, signal_rate, latency_ms,
        )
        logger.info("=== Job complete — status: success ===")

        # Print final metrics to stdout (required by Docker spec)
        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    except Exception as exc:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error("Pipeline failed: %s", exc, exc_info=True)

        error_metrics = {
            "version": version,
            "status": "error",
            "error_message": str(exc),
        }
        try:
            write_metrics(args.output, error_metrics)
        except Exception as write_exc:
            logger.error("Could not write error metrics: %s", write_exc)

        logger.info("=== Job complete — status: error ===")
        print(json.dumps(error_metrics, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
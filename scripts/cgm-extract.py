#!/usr/bin/env python3
"""Extract CGM day summaries and timestamped samples from HAE .hae files."""

import argparse
import json
import statistics
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

APPLE_EPOCH_SECONDS = 978_307_200
TZ = ZoneInfo("Asia/Shanghai")
CGM_DIR = Path.home() / (
    "Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/"
    "AutoSync/HealthMetrics/blood_glucose"
)


def glucose_path(day: str) -> Path:
    return CGM_DIR / f"{day.replace('-', '')}.hae"


def decode_hae(path: Path) -> dict:
    raw = path.read_bytes()
    if raw.startswith(b"bvx-5"):
        return json.loads(raw)
    result = subprocess.run(
        ["/usr/bin/compression_tool", "-decode", "-a", "lzfse", "-i", str(path)],
        capture_output=True,
        timeout=20,
        check=True,
    )
    return json.loads(result.stdout)


def read_samples(day: str) -> list[tuple[datetime, float]]:
    path = glucose_path(day)
    if not path.exists():
        return []
    payload = decode_hae(path)
    samples: dict[int, float] = {}
    for record in payload.get("data", []):
        try:
            value = float(record["qty"])
            timestamp = float(record["start"]) + APPLE_EPOCH_SECONDS
            unit = str(record["unit"]).lower()
        except (KeyError, TypeError, ValueError):
            continue
        if unit == "mg/dl":
            value /= 18.0182
        elif unit != "mmol/l":
            continue
        if 3.0 <= value <= 15.0:
            samples[round(timestamp)] = value
    return [(datetime.fromtimestamp(ts, TZ), value) for ts, value in sorted(samples.items())]


def rounded(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def summarize(day: str, samples: list[tuple[datetime, float]]) -> dict:
    if not samples:
        return {"date": day, "status": "no_data"}
    values = [value for _, value in samples]
    fasting = [value for stamp, value in samples if 4 <= stamp.hour < 8]
    mean = statistics.mean(values)
    return {
        "date": day,
        "status": "ok",
        "n": len(values),
        "coverage_hours": rounded((samples[-1][0] - samples[0][0]).total_seconds() / 3600, 1),
        "avg": rounded(mean),
        "min": rounded(min(values)),
        "max": rounded(max(values)),
        "cv_pct": rounded(statistics.pstdev(values) / mean * 100, 1),
        "tir_pct": rounded(sum(3.9 <= value <= 7.8 for value in values) / len(values) * 100, 1),
        "fasting_avg": rounded(statistics.mean(fasting)) if fasting else None,
        "first_at": samples[0][0].isoformat(),
        "last_at": samples[-1][0].isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="YYYY-MM-DD")
    parser.add_argument("--history-days", type=int, default=0)
    args = parser.parse_args()

    try:
        samples = read_samples(args.date)
        output = summarize(args.date, samples)
        output["samples"] = [
            {"at": stamp.isoformat(), "mmol_l": rounded(value)}
            for stamp, value in samples
        ]
        history = []
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        for offset in range(1, args.history_days + 1):
            prior = (target - timedelta(days=offset)).isoformat()
            try:
                prior_samples = read_samples(prior)
            except Exception:
                continue
            item = summarize(prior, prior_samples)
            if item["status"] == "ok":
                history.append(item)
        if args.history_days:
            output["history"] = history
    except Exception as exc:
        output = {"date": args.date, "status": "error", "error": str(exc)}

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    for row in rows:
        expected = bool(row["expected"])
        predicted = bool(row["predicted"])
        if expected and predicted:
            tp += 1
        elif not expected and predicted:
            fp += 1
        elif not expected and not predicted:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": (tp + tn) / max(tp + fp + tn + fn, 1),
    }


def evaluate(manifest: Dict[str, Any], runs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ids = [item["id"] for item in manifest["cases"]]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("manifest must contain unique, nonempty case IDs")
    if any(type(item["expected_bug"]) is not bool for item in manifest["cases"]):
        raise ValueError("ground-truth labels must be booleans")
    truth = {item["id"]: bool(item["expected_bug"]) for item in manifest["cases"]}
    output: Dict[str, Any] = {"schema_version": 1, "systems": {}, "rows": []}
    for system, run in runs.items():
        run_ids = [item["id"] for item in run["cases"]]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError(system + " has duplicate case IDs")
        missing, extra = set(truth) - set(run_ids), set(run_ids) - set(truth)
        if missing or extra:
            raise ValueError("{} cohort mismatch: missing={}, extra={}".format(
                system, sorted(missing), sorted(extra)))
        failures = [
            item["id"]
            for item in run["cases"]
            if item.get("completed") is not True
        ]
        if failures:
            raise ValueError(
                "{} has failed analyzer runs; refusing to score: {}".format(
                    system, ", ".join(failures)
                )
            )
        if any(type(item.get("prediction")) is not bool for item in run["cases"]):
            raise ValueError(system + " predictions must be explicit booleans")
        predictions = {item["id"]: item["prediction"] for item in run["cases"]}
        rows = [
            {
                "system": system,
                "id": case_id,
                "expected": expected,
                "predicted": predictions[case_id],
            }
            for case_id, expected in truth.items()
        ]
        output["rows"].extend(rows)
        output["systems"][system] = metrics(rows)
    return output


def write_evaluation(result: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["system", "id", "expected", "predicted"])
        writer.writeheader()
        writer.writerows(result["rows"])

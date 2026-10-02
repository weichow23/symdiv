import json
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List


def clang_version(clang: str) -> str:
    process = subprocess.run([clang, "--version"], capture_output=True, text=True, check=False)
    return process.stdout.splitlines()[0] if process.stdout else "unknown"


def _sarif_results(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for run in report.get("runs", []):
        for result in run.get("results", []):
            message = result.get("message", {}).get("text", "")
            locations = result.get("locations", [])
            location = locations[0].get("physicalLocation", {}) if locations else {}
            region = location.get("region", {})
            output.append(
                {
                    "rule_id": result.get("ruleId"),
                    "message": message,
                    "line": region.get("startLine"),
                    "column": region.get("startColumn"),
                }
            )
    return output


def run_baseline_case(source_path: Path, clang: str = "clang") -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="symdiv-clang-") as directory:
        report_path = Path(directory) / "report.sarif"
        command = [
            clang,
            "--analyze",
            "--analyzer-output",
            "sarif",
            "-Xanalyzer",
            "-analyzer-checker=core.DivideZero",
            "-std=c11",
            "-o",
            str(report_path),
            str(source_path),
        ]
        started = time.monotonic()
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        except subprocess.TimeoutExpired:
            return {"file": source_path.as_posix(), "prediction": False, "findings": [],
                    "elapsed_seconds": time.monotonic() - started, "returncode": None,
                    "completed": False, "stderr": "Clang timed out after 60 seconds", "command": command}
        elapsed = time.monotonic() - started
        report = {}
        if report_path.exists() and report_path.stat().st_size:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        findings = [
            finding
            for finding in _sarif_results(report)
            if "Division by zero" in finding.get("message", "")
            or "division by zero" in finding.get("message", "")
            or finding.get("rule_id") == "core.DivideZero"
        ]
        return {
            "file": source_path.as_posix(),
            "prediction": bool(findings),
            "findings": findings,
            "elapsed_seconds": elapsed,
            "returncode": process.returncode,
            "completed": process.returncode == 0 and "runs" in report,
            "stderr": process.stderr,
            "command": command,
        }


def run_baseline(manifest: Dict[str, Any], root: Path, clang: str = "clang") -> Dict[str, Any]:
    cases = []
    started = time.monotonic()
    for item in manifest["cases"]:
        result = run_baseline_case(root / item["file"], clang=clang)
        result["id"] = item["id"]
        cases.append(result)
    failures = [case["id"] for case in cases if not case["completed"]]
    return {
        "schema_version": 1,
        "analyzer": "clang-static-analyzer",
        "checker": "core.DivideZero",
        "tool_version": clang_version(clang),
        "platform": platform.platform(),
        "elapsed_seconds": time.monotonic() - started,
        "cases": cases,
        "failed_cases": failures,
    }

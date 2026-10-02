import argparse
import copy
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import z3
from .baseline import run_baseline, clang_version
from .evaluate import evaluate, write_evaluation
from .extract import extract_sites
from .ground import build_context
from .model import Hypothesis
from .provider import analyze_with_codex, analyze_with_openai, provider_result_from_response
from .verify import verify_hypothesis


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _manifest_root(manifest_path, manifest):
    return (manifest_path.parent / manifest.get("root", ".")).resolve()


def command_baseline(args):
    path = Path(args.manifest).resolve()
    manifest = _read_json(path)
    result = run_baseline(manifest, _manifest_root(path, manifest), args.clang)
    result["manifest_sha256"] = digest(path)
    result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    for case, item in zip(result["cases"], manifest["cases"]):
        case["source_sha256"] = digest(_manifest_root(path, manifest) / item["file"])
        if item.get("sha256") and item["sha256"] != case["source_sha256"]:
            raise ValueError("manifest source hash mismatch: " + item["id"])
        case["file"] = item["file"]
    _write_json(args.out, result)
    return 1 if result["failed_cases"] else 0


def replay_provider(recorded, sites, path):
    if recorded.get("source_sha256") != digest(path):
        raise ValueError("replay source hash is missing or does not match")
    provider = provider_result_from_response(copy.deepcopy(recorded["raw_response"]))
    old_sites = {f["site"]["site_id"]: f["site"] for f in recorded["findings"]}
    prior_map = provider.raw.get("_replay_site_id_map", {})
    migrated = {}
    locations = {(s.function, s.line, s.column, s.operator, s.denominator): s for s in sites}
    for hypothesis in provider.hypotheses:
        raw_id = hypothesis.site_id
        old = old_sites.get(raw_id) or old_sites.get(prior_map.get(raw_id))
        if old is None:
            raise ValueError("replay response has an unrecorded site ID")
        key = tuple(old[k] for k in ("function", "line", "column", "operator", "denominator"))
        current = locations.get(key)
        if current is None or old["function_source"] != current.function_source:
            raise ValueError("replay source site no longer matches")
        hypothesis.site_id = current.site_id
        migrated[raw_id] = current.site_id
    # Keep the original response payload unchanged and retain its explicit
    # transport mapping, so a migrated run can itself be replayed repeatedly.
    provider.raw["_replay_site_id_map"] = migrated
    return provider


def command_neuro(args):
    manifest_path = Path(args.manifest).resolve()
    manifest, config = _read_json(manifest_path), _read_json(args.config)
    root = _manifest_root(manifest_path, manifest)
    if config.get("provider") not in ("codex_exec", "openai_responses", "replay"):
        raise ValueError("unknown provider")
    prompt_path = Path(config["prompt"])
    prompt = prompt_path.read_text(encoding="utf-8")
    replay = None
    if config["provider"] == "replay":
        recorded_run = _read_json(config["replay_run"])
        replay = {c["id"]: c for c in recorded_run["cases"]}
    files = sorted(Path(__file__).parent.glob("*.py"))
    code_hash = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in files)).hexdigest()
    result = {
        "schema_version": 2, "analyzer": "symdiv-source-grounded-v2",
        "provider": config["provider"], "model": config["model"],
        "prompt": config["prompt"], "prompt_sha256": digest(prompt_path),
        "manifest_sha256": digest(manifest_path), "code_sha256": code_hash,
        "configuration": config, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "z3": z3.get_version_string(), "clang": clang_version(args.clang)},
        "cases": [], "total_tokens": 0, "model_calls": 0, "stop_reason": None,
    }
    if config.get("output_schema"):
        result["schema_sha256"] = digest(config["output_schema"])
    if replay is not None:
        result["replay_run_sha256"] = digest(config["replay_run"])
        result["replayed_model_tokens"] = 0
    started = time.monotonic()
    max_calls = int(config.get("max_calls", len(manifest["cases"])))
    max_tokens = int(config.get("max_total_tokens", 500000))
    for item in manifest["cases"]:
        case = {"id": item["id"], "file": item["file"], "prediction": None,
                "completed": False, "findings": [], "attempts": 0}
        if result["stop_reason"]:
            case["error"] = "not run: " + result["stop_reason"]
            result["cases"].append(case)
            continue
        if replay is None and (result["model_calls"] >= max_calls or result["total_tokens"] >= max_tokens):
            result["stop_reason"] = "configured call or token budget exhausted"
            case["error"] = "not run: " + result["stop_reason"]
            result["cases"].append(case)
            continue
        path = root / item["file"]
        case_started = time.monotonic()
        try:
            case["source_sha256"] = digest(path)
            if item.get("sha256") and item["sha256"] != case["source_sha256"]:
                raise ValueError("manifest source hash mismatch")
            sites = extract_sites(path, clang=args.clang)
            if not sites:
                raise ValueError("no eligible integer division/remainder sites")
            case["attempts"] = 1
            if replay is not None:
                provider = replay_provider(replay[item["id"]], sites, path)
                result["replayed_model_tokens"] += int(provider.input_tokens or 0) + int(provider.output_tokens or 0)
            else:
                result["model_calls"] += 1
                if config["provider"] == "codex_exec":
                    provider = analyze_with_codex(path.read_text(), sites, config, prompt, Path.cwd())
                else:
                    provider = analyze_with_openai(path.read_text(), sites, config, prompt)
            case["raw_response"] = provider.raw
            case["input_tokens"], case["output_tokens"] = provider.input_tokens, provider.output_tokens
            case["client_elapsed_seconds"] = provider.raw.get("_client_elapsed_seconds")
            if replay is None:
                if provider.input_tokens is None or provider.output_tokens is None:
                    result["stop_reason"] = "model usage unavailable; cannot enforce token ceiling"
                    raise ValueError(result["stop_reason"])
                result["total_tokens"] += provider.input_tokens + provider.output_tokens
                if result["total_tokens"] > max_tokens:
                    result["stop_reason"] = "token budget exceeded after completed call (overrun retained)"
            ids = [h.site_id for h in provider.hypotheses]
            if len(set(ids)) != len(ids) or set(ids) - {s.site_id for s in sites}:
                raise ValueError("duplicate or unexpected model site IDs")
            by_id = {h.site_id: h for h in provider.hypotheses}
            symbolic_started = time.monotonic()
            context = build_context(path, sites, args.clang, int(config.get("loop_bound", 8)),
                                    int(config.get("state_limit", 4096)), int(config.get("z3_timeout_ms", 5000)))
            for site in sites:
                h = by_id.get(site.site_id)
                if h is None:
                    verification = {"status": "missing", "accepted": False,
                                    "reason": "model omitted this site", "model": {}}
                else:
                    verification = verify_hypothesis(site, h, int(config.get("z3_timeout_ms", 5000)), context[site.site_id]).to_dict()
                symbolic = verify_hypothesis(site, Hypothesis(site.site_id, "bug", [], site.denominator,
                                                              "symbolic-only ablation", 1.0),
                                              int(config.get("z3_timeout_ms", 5000)), context[site.site_id]).to_dict()
                site_record = site.to_dict()
                site_record["file"] = item["file"]
                case["findings"].append({"site": site_record, "hypothesis": h.__dict__ if h else None,
                                         "verification": verification, "symbolic_only": symbolic,
                                         "exploration_incomplete": context[site.site_id].incomplete})
            case["symbolic_seconds"] = time.monotonic() - symbolic_started
            case["prediction"] = any(f["verification"]["accepted"] for f in case["findings"])
            case["llm_prediction"] = any(h.verdict == "bug" for h in provider.hypotheses)
            case["symbolic_prediction"] = any(f["symbolic_only"]["accepted"] for f in case["findings"])
            case["completed"] = True
        except Exception as error:
            case["error"] = "{}: {}".format(type(error).__name__, error)
            if replay is None and case["attempts"] and "raw_response" not in case:
                result["stop_reason"] = "provider failure with unknown token usage; stopping to preserve budget"
        case["elapsed_seconds"] = time.monotonic() - case_started
        result["cases"].append(case)
        result["elapsed_seconds"] = time.monotonic() - started
        _write_json(args.out, result)
        print("{}: {}".format(item["id"], "completed" if case["completed"] else case.get("error")), flush=True)
    result["elapsed_seconds"] = time.monotonic() - started
    result["failed_cases"] = [c["id"] for c in result["cases"] if not c["completed"]]
    _write_json(args.out, result)
    return 1 if result["failed_cases"] else 0


def command_evaluate(args):
    manifest = _read_json(args.manifest)
    runs = {"baseline": _read_json(args.baseline)}
    if args.neuro:
        runs["neuro"] = _read_json(args.neuro)
        if runs["neuro"].get("schema_version") == 2:
            for name, key in [("llm_only", "llm_prediction"), ("symbolic_only", "symbolic_prediction")]:
                runs[name] = {"cases": [{"id": c["id"], "completed": c["completed"], "prediction": c.get(key)}
                                         for c in runs["neuro"]["cases"]]}
    for name, run in runs.items():
        if run.get("manifest_sha256") and run["manifest_sha256"] != digest(args.manifest):
            raise ValueError(name + " was run against a different manifest")
    result = evaluate(manifest, runs)
    write_evaluation(result, Path(args.out_dir))
    print(json.dumps(result["systems"], indent=2))
    return 0


def parser():
    value = argparse.ArgumentParser(prog="symdiv")
    sub = value.add_subparsers(dest="command", required=True)
    for command in ("baseline", "neuro"):
        p = sub.add_parser(command)
        p.add_argument("--manifest", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--clang", default="clang")
        if command == "neuro": p.add_argument("--config", required=True)
        p.set_defaults(function=command_neuro if command == "neuro" else command_baseline)
    p = sub.add_parser("evaluate")
    p.add_argument("--manifest", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--neuro")
    p.add_argument("--out-dir", required=True)
    p.set_defaults(function=command_evaluate)
    p = sub.add_parser("extract")
    p.add_argument("source")
    p.add_argument("--clang", default="clang")
    p.set_defaults(function=lambda a: print(json.dumps([s.to_dict() for s in extract_sites(Path(a.source), a.clang)], indent=2)) or 0)
    return value


def main():
    args = parser().parse_args()
    try:
        result = args.function(args)
    except Exception as error:
        print("error: {}".format(error), file=sys.stderr)
        result = 1
    raise SystemExit(result)

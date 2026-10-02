import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from .model import DivisionSite, Hypothesis, ProviderResult


RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "site_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["bug", "safe", "unknown"]},
                    "path_conditions": {"type": "array", "items": {"type": "string"}},
                    "denominator": {"type": "string"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "site_id",
                    "verdict",
                    "path_conditions",
                    "denominator",
                    "rationale",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def _output_text(response: Dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return str(response["output_text"])
    chunks: List[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise RuntimeError("model response contains no output_text")
    return "".join(chunks)


def provider_result_from_response(response: Dict[str, Any]) -> ProviderResult:
    parsed = response.get("output") if response.get("provider") == "codex_exec" else None
    if not isinstance(parsed, dict):
        parsed = json.loads(_output_text(response))
    hypotheses = [Hypothesis.from_dict(item) for item in parsed.get("findings", [])]
    usage = response.get("usage", {})
    return ProviderResult(
        hypotheses=hypotheses,
        request_id=response.get("id"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        raw=response,
    )


def analyze_with_replay(response_path: Path) -> ProviderResult:
    if not response_path.exists():
        raise RuntimeError("replay response is missing: {}".format(response_path))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    return provider_result_from_response(response)


def analyze_with_codex(
    source: str,
    sites: List[DivisionSite],
    config: Dict[str, Any],
    prompt: str,
    workspace: Path,
) -> ProviderResult:
    site_payload = [
        {
            "site_id": site.site_id,
            "function": site.function,
            "line": site.line,
            "operator": site.operator,
            "denominator": site.denominator,
        }
        for site in sites
    ]
    full_prompt = "{}\n\nDivision sites:\n{}\n\nComplete source:\n```c\n{}\n```\n\nAnalyze only the supplied source. Do not use tools or inspect other files.".format(
        prompt,
        json.dumps(site_payload, indent=2),
        source,
    )
    schema_path = (workspace / str(config["output_schema"])).resolve()
    if not schema_path.exists():
        raise RuntimeError("Codex output schema is missing: {}".format(schema_path))

    codex_command = str(config.get("codex_command", "codex"))
    safe_environment = dict(os.environ)
    safe_environment.pop("OPENAI_API_KEY", None)
    safe_environment.pop("CODEX_API_KEY", None)
    with tempfile.TemporaryDirectory(prefix="symdiv-codex-") as directory:
        output_path = Path(directory) / "last-message.json"
        command = [
            codex_command,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--model",
            str(config["model"]),
            "-c",
            'model_reasoning_effort="{}"'.format(config.get("reasoning_effort", "medium")),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                input=full_prompt,
                cwd=directory,
                env=safe_environment,
                capture_output=True,
                text=True,
                timeout=int(config.get("timeout_seconds", 300)),
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("codex exec timed out") from error
        elapsed = time.monotonic() - started
        if process.returncode != 0:
            raise RuntimeError(
                "codex exec failed with status {}: {}".format(
                    process.returncode, process.stderr[-4000:]
                )
            )
        if not output_path.exists():
            raise RuntimeError("codex exec produced no final output file")
        output_text = output_path.read_text(encoding="utf-8")

    events = []
    for line in process.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "unparsed", "text": line})
    usage: Dict[str, Any] = {}
    thread_id = None
    for event in events:
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") == "turn.completed":
            usage = event.get("usage", {})
    if any(event.get("item", {}).get("type") not in (None, "agent_message", "reasoning")
           for event in events):
        raise RuntimeError("model used a tool; run violates source-only protocol")
    parsed = json.loads(output_text)
    hypotheses = [Hypothesis.from_dict(item) for item in parsed.get("findings", [])]
    version = subprocess.run(
        [codex_command, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return ProviderResult(
        hypotheses=hypotheses,
        request_id=thread_id,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        raw={
            "provider": "codex_exec",
            "codex_version": version,
            "model": config["model"],
            "reasoning_effort": config.get("reasoning_effort", "medium"),
            "output": parsed,
            "events": events,
            "stderr": process.stderr,
            "usage": usage,
            "_client_elapsed_seconds": elapsed,
        },
    )


def analyze_with_openai(
    source: str,
    sites: List[DivisionSite],
    config: Dict[str, Any],
    prompt: str,
) -> ProviderResult:
    key_name = str(config.get("api_key_env", "OPENAI_API_KEY"))
    api_key = os.environ.get(key_name)
    if not api_key:
        raise RuntimeError("required API key environment variable is unset: {}".format(key_name))
    base_url = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
    site_payload = [
        {
            "site_id": site.site_id,
            "function": site.function,
            "line": site.line,
            "operator": site.operator,
            "denominator": site.denominator,
        }
        for site in sites
    ]
    user_input = "Division sites:\n{}\n\nComplete source:\n```c\n{}\n```".format(
        json.dumps(site_payload, indent=2), source
    )
    body = {
        "model": config["model"],
        "instructions": prompt,
        "input": user_input,
        "max_output_tokens": int(config.get("max_output_tokens", 1800)),
        "store": bool(config.get("store", False)),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "symdiv_analysis",
                "schema": RESPONSE_SCHEMA,
                "strict": True,
            }
        },
    }
    if "temperature" in config:
        body["temperature"] = config["temperature"]
    request = urllib.request.Request(
        base_url + "/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request, timeout=int(config.get("timeout_seconds", 90))
        ) as handle:
            response = json.loads(handle.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError("model API returned HTTP {}: {}".format(error.code, detail)) from error
    response["_client_elapsed_seconds"] = time.monotonic() - started
    return provider_result_from_response(response)

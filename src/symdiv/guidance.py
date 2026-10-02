"""The neural interface for v3, kept separate from v2 predicate verification."""
import copy
import json

from .provider import RESPONSE_SCHEMA, analyze_with_codex
from .search import validate_guidance


GUIDANCE_SCHEMA = copy.deepcopy(RESPONSE_SCHEMA)
GUIDANCE_SCHEMA["properties"]["choices"] = {
    "type": "array", "items": {"type": "object", "properties": {
        "branch_id": {"type": "string"},
        "visit": {"type": "integer", "minimum": 1, "maximum": 9},
        "take": {"type": "boolean"}},
        "required": ["branch_id", "visit", "take"], "additionalProperties": False}}
GUIDANCE_SCHEMA["required"].append("choices")


def validate_response(payload, prepared):
    sites = {s.site_id:s for s in prepared["sites"]}
    findings = payload.get("findings", [])
    if len(findings) != len(sites) or {f.get("site_id") for f in findings} != set(sites):
        raise ValueError("guidance must contain exactly one finding per source site")
    for finding in findings:
        if finding.get("denominator") != sites[finding["site_id"]].denominator:
            raise ValueError("denominator does not match source")
        if finding.get("verdict") not in ("bug", "safe", "unknown") or finding.get("path_conditions") != []:
            raise ValueError("invalid verdict or nonempty neural constraints")
    return validate_guidance(payload, prepared)


def request(prepared, config, workspace, feedback=None, previous=None):
    prompt = (workspace / config["prompt"]).read_text()
    prompt += "\n\nBranch catalog:\n" + json.dumps(prepared["branches"], indent=2)
    if feedback is not None:
        prompt += "\n\nPrevious suggestion:\n" + json.dumps(previous, indent=2)
        prompt += "\n\nSource-executor feedback (no ground-truth labels):\n" + json.dumps(feedback, indent=2)
    return analyze_with_codex(prepared["path"].read_text(), prepared["sites"], config, prompt, workspace)

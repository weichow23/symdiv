import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .model import DivisionSite


def _children(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for child in node.get("inner", []):
        if isinstance(child, dict):
            yield child


def _offset(point: Dict[str, Any]) -> Optional[int]:
    if "offset" in point:
        return int(point["offset"])
    spelling = point.get("spellingLoc", {})
    if "offset" in spelling:
        return int(spelling["offset"])
    expansion = point.get("expansionLoc", {})
    if "offset" in expansion:
        return int(expansion["offset"])
    return None


def _slice(source: str, range_value: Dict[str, Any]) -> Optional[str]:
    encoded = source.encode("utf-8")
    begin = _offset(range_value.get("begin", {}))
    end_point = range_value.get("end", {})
    end = _offset(end_point)
    if begin is None or end is None:
        return None
    token_length = int(end_point.get("tokLen", 1))
    if begin < 0 or end < begin or end + token_length > len(encoded):
        return None
    return encoded[begin : end + token_length].decode("utf-8")


def _line_column(source: str, offset: int) -> tuple:
    encoded = source.encode("utf-8")
    line = encoded.count(b"\n", 0, offset) + 1
    previous = encoded.rfind(b"\n", 0, offset)
    return line, offset - previous


def _walk(node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def load_ast(path: Path, clang: str = "clang") -> Dict[str, Any]:
    if re.search(r"^\s*#", path.read_text(encoding="utf-8"), re.MULTILINE):
        raise ValueError("preprocess source first: preprocessing directives are outside this input contract")
    command = [
        clang,
        "-Xclang",
        "-ast-dump=json",
        "-fsyntax-only",
        "-std=c11",
        str(path),
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if process.returncode != 0:
        raise RuntimeError(
            "Clang AST extraction failed for {}:\n{}".format(path, process.stderr)
        )
    root = json.loads(process.stdout)
    for node in _walk(root):
        for point in node.get("range", {}).values():
            if isinstance(point, dict) and ("spellingLoc" in point or "expansionLoc" in point):
                raise ValueError("preprocess source first: macro expansions require materialized locations")
    return root


def is_integer_type(node: Dict[str, Any]) -> bool:
    value = node.get("type", {}).get("qualType", "")
    return value in {
        "int", "unsigned int", "long", "unsigned long", "long long",
        "unsigned long long", "short", "unsigned short", "char", "signed char",
        "unsigned char", "_Bool", "const int", "const unsigned int",
    }


def division_locations(source, root):
    """Keep stable legacy positions except where nested operators collide.

    Clang ranges for ``x/2*3/0`` share their beginning. For those collisions,
    use the actual operator token between the two operand ranges. Archived
    experiments can explicitly select their old catalog for faithful replay.
    """
    groups = {}
    for node in _walk(root):
        if (node.get("kind") not in ("BinaryOperator", "CompoundAssignOperator")
                or node.get("opcode") not in ("/", "%", "/=", "%=")
                or not is_integer_type(node)):
            continue
        start = _offset(node.get("range", {}).get("begin", {}))
        if start is not None:
            groups.setdefault((start, node["opcode"]), []).append(node)
    archived = os.environ.get("SYMDIV_ARCHIVED_SITE_LOCATIONS") == "1"
    encoded = source.encode("utf-8")
    result = {}
    for (start, operator), nodes in groups.items():
        for node in nodes:
            point = start
            if len(nodes) > 1 and not archived:
                left, right = list(_children(node))[:2]
                end = left["range"]["end"]
                begin = _offset(end) + int(end.get("tokLen", 1))
                finish = _offset(right["range"]["begin"])
                # Ignore comments and whitespace, preserving UTF-8 byte offsets.
                pattern = rb"(?:\s+|/\*[\s\S]*?\*/|//[^\n]*(?:\n|$))*" + re.escape(operator.encode())
                match = re.match(pattern, encoded[begin:finish])
                if match is None:
                    raise ValueError("cannot locate a distinct division operator token")
                point = begin + match.end() - len(operator)
            result[node["id"]] = _line_column(source, point)
    return result


def extract_sites(path: Path, clang: str = "clang", root=None) -> List[DivisionSite]:
    source = path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    root = root if root is not None else load_ast(path, clang)
    locations = division_locations(source, root)
    sites: List[DivisionSite] = []
    for node in _walk(root):
        if node.get("kind") != "FunctionDecl" or not node.get("name"):
            continue
        function_source = _slice(source, node.get("range", {}))
        if not function_source or not any(c.get("kind") == "CompoundStmt" for c in _children(node)):
            continue
        for candidate in _walk(node):
            if candidate.get("kind") not in ("BinaryOperator", "CompoundAssignOperator"):
                continue
            operator = candidate.get("opcode")
            if operator not in ("/", "%", "/=", "%=") or not is_integer_type(candidate):
                continue
            operands = list(_children(candidate))
            if len(operands) < 2:
                continue
            denominator = _slice(source, operands[1].get("range", {}))
            start = _offset(candidate.get("range", {}).get("begin", {}))
            if denominator is None or start is None:
                continue
            line, column = locations[candidate["id"]]
            identity = "{}:{}:{}:{}:{}".format(source_hash, node["name"], line, column, operator)
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            sites.append(
                DivisionSite(
                    site_id="div-{}".format(digest),
                    file=path.as_posix(),
                    function=str(node["name"]),
                    line=line,
                    column=column,
                    operator=str(operator),
                    denominator=denominator.strip(),
                    function_source=function_source.strip(),
                )
            )
    unique = {site.site_id: site for site in sites}
    return sorted(unique.values(), key=lambda item: (item.line, item.column))

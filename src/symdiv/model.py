from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DivisionSite:
    site_id: str
    file: str
    function: str
    line: int
    column: int
    operator: str
    denominator: str
    function_source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    site_id: str
    verdict: str
    path_conditions: List[str]
    denominator: str
    rationale: str
    confidence: float

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Hypothesis":
        return cls(
            site_id=str(value["site_id"]),
            verdict=str(value["verdict"]),
            path_conditions=[str(item) for item in value.get("path_conditions", [])],
            denominator=str(value.get("denominator", "")),
            rationale=str(value.get("rationale", "")),
            confidence=float(value.get("confidence", 0.0)),
        )


@dataclass
class Verification:
    status: str
    accepted: bool
    reason: str
    model: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderResult:
    hypotheses: List[Hypothesis]
    request_id: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    raw: Dict[str, Any]


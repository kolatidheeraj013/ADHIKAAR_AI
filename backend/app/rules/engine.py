"""Pure, deterministic evaluation of validated MOCK scheme rules.

The language model may extract facts, but this module is the only component
allowed to decide eligibility.  It deliberately accepts a tiny expression
subset and delegates the actual evaluation to ``simpleeval``—never ``eval``.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from simpleeval import SimpleEval

SCHEMES_DIR = Path(__file__).parent / "schemes"
FactType = Literal["float", "int", "str", "bool"]


class SchemeValidationError(ValueError):
    """Raised when a scheme file is malformed or unsafe to load."""


class DecisionOutcome(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNDETERMINED = "UNDETERMINED"


class RuleStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    type: FactType
    source: str = Field(min_length=1)
    question: str | None = None

    @field_validator("key", "source")
    @classmethod
    def identifier_must_be_safe(cls, value: str) -> str:
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("fact keys and sources must be safe identifiers")
        return value


class PayloadField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    type: FactType
    source: str = Field(min_length=1)

    @field_validator("key", "source")
    @classmethod
    def identifier_must_be_safe(cls, value: str) -> str:
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("payload keys and sources must be safe identifiers")
        return value


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    expr: str = Field(min_length=1)
    fail_reason: str = Field(min_length=1)


class Scheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    benefit: str = Field(min_length=1)
    required_documents: list[str]
    facts: list[FactSpec]
    payload_fields: list[PayloadField]
    rules: list[RuleSpec]

    @model_validator(mode="after")
    def validate_scheme_contract(self) -> "Scheme":
        if "MOCK" not in self.name.upper() or "MOCK" not in self.benefit.upper():
            raise ValueError("scheme name and benefit must be explicitly labeled MOCK")

        _require_unique("required_documents", self.required_documents)
        fact_keys = _require_unique("facts", [fact.key for fact in self.facts])
        payload_keys = _require_unique(
            "payload_fields", [field.key for field in self.payload_fields]
        )
        rule_ids = _require_unique("rules", [rule.id for rule in self.rules])

        for fact in self.facts:
            if fact.source == "declaration":
                if fact.type not in {"bool", "str"}:
                    raise ValueError("declaration facts must be boolean or short text choices")
                if not fact.question:
                    raise ValueError(f"declaration fact {fact.key!r} needs a question")

        for rule in self.rules:
            names = _expression_names(rule.expr)
            unknown_names = sorted(set(names) - set(fact_keys))
            if unknown_names:
                raise ValueError(
                    f"rule {rule.id!r} references undeclared facts: {', '.join(unknown_names)}"
                )

        duplicate_payload_overlap = set(payload_keys) & set(fact_keys)
        if duplicate_payload_overlap:
            raise ValueError(
                "payload fields must be separate from rule facts: "
                + ", ".join(sorted(duplicate_payload_overlap))
            )
        if len(rule_ids) != len(self.rules):
            raise AssertionError("unreachable: _require_unique validates rule ids")
        return self


class RuleTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    status: RuleStatus
    facts_used: list[str]
    source_doc_ids: list[str]
    reason: str


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: DecisionOutcome
    trace: list[RuleTrace]

    @property
    def rule_trace(self) -> list[RuleTrace]:
        """Compatibility name used by the wider agent state contract."""
        return self.trace


class _NormalizedFact:
    def __init__(self, value: Any, source_doc_id: str | None) -> None:
        self.value = value
        self.source_doc_id = source_doc_id


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Compare,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


def _require_unique(label: str, values: Sequence[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicate entries")
    return list(values)


def _expression_names(expression: str) -> list[str]:
    """Validate the expression grammar and return names in source order."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid rule expression: {exc.msg}") from exc

    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(
                f"unsupported syntax in rule expression: {type(node).__name__}"
            )
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise ValueError("private names are not allowed in rule expressions")
            if node.id not in names:
                names.append(node.id)
        if isinstance(node, ast.Constant) and not isinstance(
            node.value, (bool, int, float, str, type(None))
        ):
            raise ValueError("only scalar constants are allowed in rule expressions")
    return names


def load_scheme(path: str | Path) -> Scheme:
    """Load and validate one YAML scheme, failing closed on any error."""
    scheme_path = Path(path)
    try:
        raw = yaml.safe_load(scheme_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("scheme YAML must contain a mapping at the root")
        return Scheme.model_validate(raw)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        if isinstance(exc, SchemeValidationError):
            raise
        raise SchemeValidationError(f"invalid scheme {scheme_path}: {exc}") from exc


def load_schemes(directory: str | Path = SCHEMES_DIR) -> dict[str, Scheme]:
    """Load all YAML schemes in a directory, keyed by their stable id."""
    scheme_dir = Path(directory)
    if not scheme_dir.is_dir():
        raise SchemeValidationError(f"scheme directory does not exist: {scheme_dir}")

    schemes: dict[str, Scheme] = {}
    for path in sorted((*scheme_dir.glob("*.yaml"), *scheme_dir.glob("*.yml"))):
        scheme = load_scheme(path)
        if scheme.scheme_id in schemes:
            raise SchemeValidationError(f"duplicate scheme_id: {scheme.scheme_id}")
        schemes[scheme.scheme_id] = scheme
    if not schemes:
        raise SchemeValidationError(f"no YAML schemes found in {scheme_dir}")
    return schemes


def evaluate(scheme: Scheme, facts: Mapping[str, Any]) -> DecisionResult:
    """Evaluate every rule and return a tri-state decision plus an audit trace."""
    traces: list[RuleTrace] = []
    has_unknown = False
    has_failure = False

    for rule in scheme.rules:
        fact_names = _expression_names(rule.expr)
        normalized = {
            name: _normalize_fact(facts[name]) for name in fact_names if name in facts
        }
        missing = [name for name in fact_names if name not in normalized]
        source_doc_ids = _source_doc_ids(normalized.values())
        if missing:
            has_unknown = True
            traces.append(
                RuleTrace(
                    rule_id=rule.id,
                    status=RuleStatus.UNKNOWN,
                    facts_used=fact_names,
                    source_doc_ids=source_doc_ids,
                    reason="Missing fact(s): " + ", ".join(missing),
                )
            )
            continue

        values = {name: fact.value for name, fact in normalized.items()}
        try:
            result = _evaluate_expression(rule.expr, values)
        except Exception as exc:  # simpleeval errors are not eligibility outcomes.
            raise SchemeValidationError(
                f"rule {rule.id!r} could not be evaluated safely: {exc}"
            ) from exc
        if not isinstance(result, bool):
            raise SchemeValidationError(f"rule {rule.id!r} must evaluate to a boolean")

        status = RuleStatus.PASSED if result else RuleStatus.FAILED
        has_failure = has_failure or not result
        traces.append(
            RuleTrace(
                rule_id=rule.id,
                status=status,
                facts_used=fact_names,
                source_doc_ids=source_doc_ids,
                reason="Rule passed." if result else rule.fail_reason,
            )
        )

    if has_failure:
        outcome = DecisionOutcome.NOT_ELIGIBLE
    elif has_unknown:
        outcome = DecisionOutcome.UNDETERMINED
    else:
        outcome = DecisionOutcome.ELIGIBLE
    return DecisionResult(outcome=outcome, trace=traces)


def _evaluate_expression(expression: str, values: Mapping[str, Any]) -> Any:
    evaluator = SimpleEval()
    evaluator.names = dict(values)
    return evaluator.eval(expression)


def _normalize_fact(raw: Any) -> _NormalizedFact:
    if isinstance(raw, Mapping) and "value" in raw:
        source_doc_id = raw.get("source_doc_id")
        return _NormalizedFact(raw["value"], source_doc_id if source_doc_id else None)
    if hasattr(raw, "value"):
        source_doc_id = getattr(raw, "source_doc_id", None)
        return _NormalizedFact(raw.value, source_doc_id if source_doc_id else None)
    return _NormalizedFact(raw, None)


def _source_doc_ids(facts: Sequence[_NormalizedFact] | Any) -> list[str]:
    ids: list[str] = []
    for fact in facts:
        if fact.source_doc_id and fact.source_doc_id not in ids:
            ids.append(fact.source_doc_id)
    return ids

"""Write frontend/src/lib/types.generated.ts from the Pydantic contracts."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel

from ccvie.contracts.entities import (
    IssueType,
    Pack,
    PackType,
    Product,
    Region,
    Verbatim,
    VerbatimSource,
)
from ccvie.contracts.insight import InsightResponse
from ccvie.contracts.query import QueryFilters, QueryRequest
from ccvie.contracts.router import RouteDecision

CONST_NAMES = {
    "IssueType": "ISSUE_TYPES",
    "PackType": "PACK_TYPES",
    "VerbatimSource": "VERBATIM_SOURCES",
    "RouteDecision": "ROUTE_DECISIONS",
}

ENUMS = (IssueType, PackType, VerbatimSource, RouteDecision)
MODELS = (Product, Pack, Region, Verbatim, InsightResponse, QueryFilters, QueryRequest)
OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "types.generated.ts"


def unwrap(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def ts_type(annotation: object) -> str:
    annotation = unwrap(annotation)
    origin = get_origin(annotation)
    if annotation in (datetime,):
        return "Date"
    if annotation is UUID or annotation is str:
        return "string"
    if annotation in (int, float):
        return "number"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation.__name__
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__
    if origin is list:
        return f"{ts_type(get_args(annotation)[0])}[]"
    raise TypeError(f"unsupported contract type: {annotation!r}")


def render_enum(enum_cls: type[Enum]) -> str:
    const_name = CONST_NAMES[enum_cls.__name__]
    values = ", ".join(f'"{member.value}"' for member in enum_cls)
    return (
        f"export const {const_name} = [{values}] as const;\n"
        f"export type {enum_cls.__name__} = (typeof {const_name})[number];"
    )


def render_model(model: type) -> str:
    lines = [f"export interface {model.__name__} {{"]
    for name, field in model.model_fields.items():
        rendered = ts_type(field.annotation)
        if field.is_required():
            lines.append(f"  {name}: {rendered};")
        else:
            lines.append(f"  {name}?: {rendered};")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    parts = [
        "// GENERATED — do not edit. Source: backend/src/ccvie/contracts/",
        "// ponytail: Date fields, not ISO strings. "
        "api-client parses HTTP JSON when a route exists.",
        "",
    ]
    parts.extend(render_enum(enum_cls) for enum_cls in ENUMS)
    parts.append("")
    parts.extend(render_model(model) for model in MODELS)
    parts.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()

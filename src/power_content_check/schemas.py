"""JSON Schemas for the run report and the catalog, built from the model.

The report is this tool's interface, and until now its shape was described only
by Python: ``tests/test_report.py`` pins the key sets and ADR 0010 states the
append-only policy, but a stranger's script had nothing to validate against.
This module builds the two schema documents, ``scripts/gen_schemas.py`` writes
them to ``schemas/``, and ``tests/test_schemas.py`` fails if the committed files
and this module disagree.

Three things are built here rather than typed, so they cannot drift from the
code they describe:

**The enumerations.** ``Status``, ``Basis``, ``Blocker`` and ``Readability`` are
read off the ``StrEnum`` classes. A new status is in the schema the moment it is
in the model.

**The exit codes.** Read off ``ExitCode``. The schema's ``exit_code`` therefore
cannot permit a code the tool does not define, or forbid one it does.

**The set of check ids the report must carry.** The fail-closed contract says a
report accounts for every registered check, including the ones that enforce
nothing: ``docs/adr/0002``. That was previously a property of the engine and a
test. Here it is a property of the format, expressed as one ``contains`` clause
per registered id, so a report that quietly dropped a not-evaluated check is
*invalid* rather than merely smaller than expected. A consumer validating a
report gets the same guarantee this repo's own tests do.

What is deliberately NOT derived: the property maps. ``to_dict`` is not a
mechanical dump of the dataclass fields -- ``counts``, ``summary`` and
``exit_code`` are computed, and ``Citation.to_dict`` flattens its source into
five keys -- so deriving properties from ``dataclasses.fields`` would describe a
shape the tool does not emit. The maps are written once, here, and
``tests/test_schemas.py`` holds them equal to real reports and to the dataclass
fields, which is the check that actually catches a drifting shape.

``additionalProperties: false`` everywhere is load-bearing: under ADR 0010 a new
key is a deliberate minor bump, and a schema that tolerated unknown keys would
let one arrive without anybody noticing.
"""

from __future__ import annotations

import json
from typing import Any, Final

from .advisory import ADVISORY_CODES, NOTICE
from .model import (
    CATALOG_SCHEMA_ID,
    REPORT_SCHEMA_ID,
    SCHEMA_VERSION,
    Basis,
    Blocker,
    ExitCode,
    Readability,
    Status,
)

_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"

_APPEND_ONLY: Final = (
    "Schema version 1. Within one version every key is append only: removing a "
    "key, renaming one, or changing what a key holds is a breaking change and "
    "moves schema_version. See docs/adr/0010. additionalProperties is false "
    "everywhere, so a key this schema does not know about is a validation "
    "failure rather than a silent addition."
)


def _enum(values: Any) -> list[str]:
    return [member.value for member in values]


def _nullable(kind: str, description: str) -> dict[str, Any]:
    """A field the tool sets to null when it has nothing to report.

    ``null`` is spelled out rather than allowed by omission. A page count the
    tool could not read is not a page count of zero, and the schema has to be
    able to tell a consumer which of the two it is holding.
    """
    return {"type": [kind, "null"], "description": description}


def _evidence_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["page", "run", "truncated", "partial", "cell_index"],
        "properties": {
            "page": _nullable(
                "integer",
                "1-based page the run was read from, or null when it cannot be "
                "attributed to one page: plain-text input, or a run that exists "
                "only in the join of two pages. Never 0, and never guessed.",
            ),
            "run": {
                "type": "string",
                "description": (
                    "The normalised text run the check matched, bounded. Normalised, "
                    "not verbatim: it is the form the check compared against, so a "
                    "reader reproduces the match rather than the typography."
                ),
            },
            "truncated": {
                "type": "boolean",
                "description": (
                    "True when the run was cut to the reporting cap. A cut run "
                    "carries an ellipsis at the cut, so a quotation is never "
                    "silently shortened."
                ),
            },
            "partial": {
                "type": "boolean",
                "description": (
                    "True when the run is the nearest thing the check found rather "
                    "than the thing the requirement asks for. Only ever set on a "
                    "deviation."
                ),
            },
            "cell_index": _nullable(
                "integer",
                "Index of the reconstructed column cell the run was found in, when "
                "ADR 0008's column reading supplied it; null otherwise. Cells are "
                "read from the page-joined document, so they carry no page.",
            ),
        },
    }


def _check_result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["check_id", "status", "finding", "detail", "evidence"],
        "properties": {
            "check_id": {
                "type": "string",
                "description": "The registered check this result is about.",
            },
            "status": {
                "enum": _enum(Status),
                "description": (
                    "not_evaluated is never a pass. A run that could not measure "
                    "something says so here and in the exit code."
                ),
            },
            "finding": {"type": "string"},
            "detail": _nullable("string", "Further explanation, or null."),
            "evidence": {
                "oneOf": [{"$ref": "#/$defs/evidence"}, {"type": "null"}],
                "description": (
                    "Where the run this check matched was read from, or null. Null "
                    "has three causes and none of them is a claim about the "
                    "document: collection was off, nothing was matched (an absence "
                    "has no position), or the run could not be located. It never "
                    "means somewhere else. Nothing here can change a status."
                ),
            },
        },
    }


def _advisory_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "observation", "where", "notice"],
        "description": (
            "An observation no published requirement covers. It carries no "
            "status, is in no count and reaches no exit code. See docs/adr/0013."
        ),
        "properties": {
            "code": {"enum": list(ADVISORY_CODES)},
            "observation": {"type": "string"},
            "where": {"type": "string"},
            "notice": {
                "const": NOTICE,
                "description": (
                    "Fixed text, attached by the type rather than by the caller, "
                    "so every advisory carries the same disclaimer."
                ),
            },
        },
    }


def _counts_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": _enum(Status),
        "properties": {status.value: {"type": "integer", "minimum": 0} for status in Status},
    }


def _document_schema(check_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "path",
            "readability",
            "unreadable_reason",
            "sha256",
            "page_count",
            "image_count",
            "vector_shape_count",
            "extraction_basis",
            "counts",
            "results",
            "advisories",
        ],
        "properties": {
            "path": {"type": "string"},
            "readability": {"enum": _enum(Readability)},
            "unreadable_reason": _nullable(
                "string", "Why the document could not be read, or null when it was read."
            ),
            "sha256": _nullable("string", "Digest of the bytes checked, or null."),
            "page_count": _nullable(
                "integer", "Pages, or null when the input is not paginated or could not be read."
            ),
            "image_count": _nullable(
                "integer",
                (
                    "Raster images the document declares, or null when that is unknown. "
                    "Not a regulatory quantity: it qualifies what an absence finding is "
                    "entitled to mean. Null is not zero."
                ),
            ),
            "vector_shape_count": _nullable(
                "integer",
                (
                    "Times the document paints a vector path, or null when unknown. "
                    "See docs/adr/0012. Null is not zero."
                ),
            ),
            "extraction_basis": _nullable(
                "string", "What the tool was able to look at, or null when it read nothing."
            ),
            "counts": _counts_schema(),
            "results": {
                "type": "array",
                "items": {"$ref": "#/$defs/check_result"},
                "description": (
                    "Every registered check, whether or not it enforces anything. "
                    "The allOf below requires each registered id to appear, so a "
                    "report that dropped a not-evaluated check is invalid."
                ),
                "allOf": [
                    {
                        "contains": {
                            "type": "object",
                            "required": ["check_id"],
                            "properties": {"check_id": {"const": check_id}},
                        }
                    }
                    for check_id in check_ids
                ],
            },
            "advisories": {"type": "array", "items": {"$ref": "#/$defs/advisory"}},
        },
    }


def _summary_schema() -> dict[str, Any]:
    keys = (
        "documents_checked",
        "documents_readable",
        "documents_unreadable",
        "conforms",
        "does_not_conform",
        "not_evaluated",
        "advisories",
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(keys),
        "properties": {key: {"type": "integer", "minimum": 0} for key in keys},
    }


def _exit_codes() -> list[int]:
    return sorted(value for name, value in vars(ExitCode).items() if not name.startswith("_"))


def report_schema(check_ids: tuple[str, ...]) -> dict[str, Any]:
    """The schema for what ``power-content-check check --json`` writes."""
    return {
        "$schema": _DIALECT,
        "$id": REPORT_SCHEMA_ID,
        "title": "power-content-check run report",
        "description": _APPEND_ONLY,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "schema_version",
            "tool",
            "tool_version",
            "ruleset_id",
            "ruleset_effective",
            "generated_at",
            "notice",
            "skipped",
            "summary",
            "exit_code",
            "documents",
        ],
        "properties": {
            "schema": {
                "const": REPORT_SCHEMA_ID,
                "description": "Where the contract this report claims to meet is published.",
            },
            "schema_version": {"const": SCHEMA_VERSION},
            "tool": {"type": "string"},
            "tool_version": {"type": "string"},
            "ruleset_id": {"type": "string"},
            "ruleset_effective": {"type": "string"},
            "generated_at": {"type": "string"},
            "notice": {
                "type": "string",
                "description": (
                    "The standing disclaimer. A deviation is a property of a "
                    "document, not a compliance determination and not evidence "
                    "of anything a named supplier did."
                ),
            },
            "skipped": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Files inside a named directory that are not a supported label "
                    "format. Named rather than dropped in silence. Not documents, "
                    "and in no count."
                ),
            },
            "summary": _summary_schema(),
            "exit_code": {
                "enum": _exit_codes(),
                "description": (
                    "Highest first: 3 nothing was checked, 2 something could not be "
                    "evaluated, 1 a deviation was found, 0 every implemented check "
                    "conformed. An empty denominator is never a pass."
                ),
            },
            "documents": {"type": "array", "items": {"$ref": "#/$defs/document"}},
        },
        "$defs": {
            "document": _document_schema(check_ids),
            "check_result": _check_result_schema(),
            "evidence": _evidence_schema(),
            "advisory": _advisory_schema(),
        },
    }


def catalog_schema() -> dict[str, Any]:
    """The schema for what ``power-content-check catalog --json`` writes."""
    return {
        "$schema": _DIALECT,
        "$id": CATALOG_SCHEMA_ID,
        "title": "power-content-check check catalog",
        "description": _APPEND_ONLY,
        "type": "array",
        "items": {"$ref": "#/$defs/check_spec"},
        "$defs": {
            "check_spec": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "title",
                    "basis",
                    "implemented",
                    "what_it_looks_for",
                    "unimplemented_reason",
                    "blocker",
                    "citation",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "basis": {"enum": _enum(Basis)},
                    "implemented": {"type": "boolean"},
                    "what_it_looks_for": {"type": "string"},
                    "unimplemented_reason": _nullable(
                        "string",
                        "Why a registered check enforces nothing, or null when it does.",
                    ),
                    "blocker": {
                        "oneOf": [{"enum": _enum(Blocker)}, {"type": "null"}],
                        "description": (
                            "Whether an unimplemented check can ever be implemented. "
                            "Null when the check is implemented."
                        ),
                    },
                    "citation": {"$ref": "#/$defs/citation"},
                },
                "allOf": [
                    {
                        "description": (
                            "A check that enforces nothing must say why and must say "
                            "whether that is permanent. CheckSpec refuses the other "
                            "combinations at construction; this is the same rule, "
                            "stated in the format."
                        ),
                        "if": {"properties": {"implemented": {"const": False}}},
                        "then": {
                            "properties": {
                                "unimplemented_reason": {"type": "string", "minLength": 1},
                                "blocker": {"enum": _enum(Blocker)},
                            }
                        },
                        "else": {
                            "properties": {
                                "unimplemented_reason": {"type": "null"},
                                "blocker": {"type": "null"},
                            }
                        },
                    }
                ],
            },
            "citation": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_key",
                    "source_title",
                    "source_url",
                    "source_effective",
                    "source_retrieved",
                    "locator",
                    "quote",
                ],
                "properties": {
                    "source_key": {"type": "string"},
                    "source_title": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_effective": _nullable(
                        "string", "When the cited text took effect, or null when unstated."
                    ),
                    "source_retrieved": {"type": "string"},
                    "locator": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
    }


def registered_check_ids() -> tuple[str, ...]:
    """The ids a report must account for, in catalog order."""
    from .checks import CHECKS

    return tuple(registered.spec.id for registered in CHECKS)


def render(document: dict[str, Any]) -> str:
    """Serialise a schema exactly as the committed files hold it."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"

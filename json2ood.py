#!/usr/bin/env python3

"""Convert nf-core JSON schema files into Open OnDemand form fragments."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union


SKIPPED_DEFINITION_NAMES = {
    "institutional_config_options",
    "generic_options",
    "max_job_request_options",
    "deprecated_options",
}

DEFAULT_HIDDEN_PROPERTY_NAMES = {
    "report_file",
    "citations_file",
    "css_file",
    "logo_file",
    "report_template",
    "report_logo",
    "report_css",
}

ALWAYS_INCLUDE_HIDDEN = {"igenomes_base", "igenomes_ignore"}
PATH_FORMATS = {"file-path", "path", "directory-path"}
STATIC_FORM_FIELDS = [
    "bc_num_hours",
    "nextflow_version",
    "executor",
    "partition",
    "num_cores",
    "num_memory",
    "workdir",
]
TRAILING_FORM_FIELDS = ["resume", "bc_email_on_started"]


# Values that can appear in a JSON Schema ``default`` or ``enum``.
# Defined with typing.Union (not "X | Y") so the module loads on
# Python 3.8/3.9, which are still common on HPC login/compute nodes.
SchemaValue = Union[str, int, float, bool, None]


@dataclass(frozen=True)
class FieldSpec:
    """Normalized representation of a schema property."""

    original_name: str
    normalized_name: str
    label: str
    help_text: str
    widget_type: str | None
    required: bool
    default_value: SchemaValue = None
    enum_values: tuple[SchemaValue, ...] = ()


@dataclass(frozen=True)
class GroupSpec:
    """Normalized representation of a schema definition group."""

    name: str
    normalized_name: str
    label: str
    help_text: str
    fields: tuple[FieldSpec, ...] = field(default_factory=tuple)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate OOD form YAML and Nextflow params templates from a JSON schema."
    )
    parser.add_argument("schema_json", help="Path to nextflow_schema.json")
    parser.add_argument("output_form_yml", help="Rendered OOD form YAML output path")
    parser.add_argument("base_form_yml", help="Base OOD form template path")
    parser.add_argument("output_params_json", help="Rendered OOD params ERB template path")
    parser.add_argument(
        "base_params_erb",
        help="Base ERB template for nf-params.json.erb (contains __NF_PARAMS_ENTRIES__ placeholder)",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schema_definitions(schema: dict[str, Any]) -> dict[str, Any]:
    definitions = schema.get("definitions", schema.get("$defs", {}))
    if not definitions:
        raise ValueError("Schema does not contain 'definitions' or '$defs'.")
    return definitions


def first_line(value: str | None) -> str:
    if not value:
        return ""
    return value.splitlines()[0].strip()


def yaml_single_quote(value: Any) -> str:
    """Render a scalar as a YAML-safe single-quoted string."""

    text = "" if value is None else str(value)
    return "'" + text.replace("'", "''") + "'"


def normalize_key(name: str) -> str:
    """Convert schema keys into stable OOD context identifiers.

    Rules:
    - lowercase everything
    - map non-alphanumeric runs to underscores
    - move digits in each token to the end of that token
    - if a token contains only digits, prefix it with ``n``
    """

    lowered = name.lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)

    segments = []
    for raw_segment in lowered.split("_"):
        if not raw_segment:
            continue

        letters = re.sub(r"\d", "", raw_segment)
        digits = re.sub(r"\D", "", raw_segment)
        if letters:
            normalized_segment = f"{letters}{digits}"
        else:
            normalized_segment = f"n{digits}"

        segments.append(normalized_segment)

    normalized = "_".join(segments)
    return normalized or "field"


def infer_widget_type(property_schema: dict[str, Any]) -> str | None:
    property_type = property_schema.get("type", "")
    if isinstance(property_type, list):
        property_type = next((item for item in property_type if item != "null"), "")
    property_type = str(property_type).strip().lower()
    property_format = str(property_schema.get("format", "")).strip().lower()

    if property_schema.get("enum"):
        return "select"
    if property_type == "boolean":
        return "check_box"
    if property_type == "string":
        return "path_selector" if property_format in PATH_FORMATS else "text_field"
    if property_type in {"integer", "number"}:
        return "number_field"
    return None


def should_skip_property(property_name: str, property_schema: dict[str, Any]) -> bool:
    if property_name == "email":
        return True
    if property_name in DEFAULT_HIDDEN_PROPERTY_NAMES:
        return True
    if property_schema.get("hidden", False) and property_name not in ALWAYS_INCLUDE_HIDDEN:
        return True
    return False


def normalize_field(
    property_name: str,
    property_schema: dict[str, Any],
    required_fields: set[str],
) -> FieldSpec | None:
    if should_skip_property(property_name, property_schema):
        return None

    return FieldSpec(
        original_name=property_name,
        normalized_name=normalize_key(property_name),
        label=str(property_schema.get("title") or property_name),
        help_text=first_line(property_schema.get("description")),
        widget_type=infer_widget_type(property_schema),
        required=property_name in required_fields,
        default_value=property_schema.get("default"),
        enum_values=tuple(property_schema.get("enum", ())),
    )


def normalize_group(group_name: str, definition: dict[str, Any]) -> GroupSpec | None:
    if group_name in SKIPPED_DEFINITION_NAMES:
        return None

    required_fields = set(definition.get("required", []))
    fields = tuple(
        field_spec
        for property_name, property_schema in definition.get("properties", {}).items()
        for field_spec in [normalize_field(property_name, property_schema, required_fields)]
        if field_spec is not None
    )

    return GroupSpec(
        name=group_name,
        normalized_name=normalize_key(group_name),
        label=str(definition.get("title") or group_name.replace("_", " ").title()),
        help_text=first_line(definition.get("description")),
        fields=fields,
    )


def normalize_schema(schema: dict[str, Any]) -> list[GroupSpec]:
    definitions = load_schema_definitions(schema)
    groups = []
    for group_name, definition in definitions.items():
        group = normalize_group(group_name, definition)
        if group is not None:
            groups.append(group)
    return groups


def render_group(group: GroupSpec) -> list[str]:
    lines = [
        f"  {group.normalized_name}:",
        f"    label: {yaml_single_quote(group.label)}",
        "    widget: 'check_box'",
        "    html_options:",
        "      data:",
    ]

    for field_spec in group.fields:
        lines.append(f"        hide-{field_spec.normalized_name}-when-un-checked: true")

    if group.help_text:
        lines.append(f"    help: {yaml_single_quote(group.help_text)}")

    lines.append("")
    return lines


def render_select_options(default_value: Any, enum_values: tuple[Any, ...]) -> list[str]:
    values = list(enum_values)
    lines = ["    options:"]

    if default_value in values:
        values.remove(default_value)

    if default_value is None:
        lines.append("      - ['', '']")
    else:
        quoted = yaml_single_quote(default_value)
        lines.append(f"      - [{quoted}, {quoted}]")

    for value in values:
        quoted = yaml_single_quote(value)
        lines.append(f"      - [{quoted}, {quoted}]")

    return lines


def render_field(field_spec: FieldSpec) -> list[str]:
    lines = [
        f"  {field_spec.normalized_name}:",
        f"    label: {yaml_single_quote(field_spec.label)}",
    ]

    if field_spec.required:
        lines.append("    required: true")

    if field_spec.widget_type == "check_box":
        # Render booleans as a two-option select so the OOD form picks up
        # data-hide-...-when-un-checked rules consistently. The default option
        # is listed first so OOD treats it as the initial selection.
        lines.append("    widget: select")
        is_default_true = field_spec.default_value is True
        default_str = "true" if is_default_true else "false"
        other_str = "false" if is_default_true else "true"
        lines.append("    options:")
        lines.append(f"      - ['{default_str}', '{default_str}']")
        lines.append(f"      - ['{other_str}', '{other_str}']")
        if isinstance(field_spec.default_value, bool):
            lines.append(f"    value: {default_str}")
    elif field_spec.widget_type == "text_field":
        lines.append("    widget: text_field")
        if field_spec.default_value not in (None, ""):
            lines.append(f"    value: {yaml_single_quote(field_spec.default_value)}")
    elif field_spec.widget_type == "path_selector":
        lines.append("    widget: path_selector")
        if field_spec.default_value not in (None, ""):
            lines.append(f"    value: {yaml_single_quote(field_spec.default_value)}")
        lines.append('    directory: "<%= ENV.fetch(\'NF2OOD_DEFAULT_DIRECTORY\', ENV.fetch(\'HOME\', \'/\')) %>"')
        lines.append("    favorites:")
        lines.append('      - "<%= ENV.fetch(\'HOME\', \'/\') %>"')
    elif field_spec.widget_type == "number_field":
        lines.append("    widget: number_field")
        # bool is a subclass of int in Python, so an explicit bool check is
        # needed to keep "value: True" / "value: False" from leaking into the
        # YAML when a schema (unusually) types a flag as a number with a
        # boolean default.
        if (
            isinstance(field_spec.default_value, (int, float))
            and not isinstance(field_spec.default_value, bool)
        ):
            lines.append(f"    value: {field_spec.default_value}")
        lines.append("    step: 1")
    elif field_spec.widget_type == "select":
        lines.append("    widget: select")
        lines.extend(render_select_options(field_spec.default_value, field_spec.enum_values))

    if field_spec.help_text:
        lines.append(f"    help: {yaml_single_quote(field_spec.help_text)}")

    lines.append("")
    return lines


def render_form(groups: list[GroupSpec], base_form_content: str) -> str:
    lines = [base_form_content.rstrip(), "", ""]
    field_order = [*STATIC_FORM_FIELDS]

    for group in groups:
        lines.extend(render_group(group))
        field_order.append(group.normalized_name)
        for field_spec in group.fields:
            lines.extend(render_field(field_spec))
            field_order.append(field_spec.normalized_name)

    lines.append("form:")
    lines.extend(f"  - {field_name}" for field_name in field_order)
    lines.extend(f"  - {field_name}" for field_name in TRAILING_FORM_FIELDS)
    lines.append("")
    return "\n".join(lines)


def render_params_entry(field_spec: FieldSpec) -> str:
    if field_spec.widget_type == "check_box":
        value_expression = f"to_bool.call(context.{field_spec.normalized_name})"
    elif field_spec.widget_type == "number_field":
        value_expression = f"to_number.call(context.{field_spec.normalized_name})"
    else:
        value_expression = f"context.{field_spec.normalized_name}"

    return f'    "{field_spec.original_name}": {value_expression}'


NF_PARAMS_ENTRIES_PLACEHOLDER = "__NF_PARAMS_ENTRIES__"


def render_params(groups: list[GroupSpec], base_params_content: str) -> str:
    """Substitute the rendered param entries into the base ERB template.

    The base template (nf-params.template.erb) carries the Ruby helpers
    (to_bool / to_number) and the surrounding params hash boilerplate; this
    function just splices the per-field entries into the
    ``__NF_PARAMS_ENTRIES__`` placeholder.
    """
    if NF_PARAMS_ENTRIES_PLACEHOLDER not in base_params_content:
        raise ValueError(
            f"Base params template is missing the {NF_PARAMS_ENTRIES_PLACEHOLDER} placeholder."
        )

    entries = [
        render_params_entry(field_spec)
        for group in groups
        for field_spec in group.fields
    ]
    return base_params_content.replace(
        NF_PARAMS_ENTRIES_PLACEHOLDER, ",\n".join(entries)
    )


def generate_outputs(
    schema: dict[str, Any],
    base_form_path: Path,
    base_params_path: Path,
) -> tuple[str, str]:
    groups = normalize_schema(schema)
    base_form_content = base_form_path.read_text(encoding="utf-8")
    base_params_content = base_params_path.read_text(encoding="utf-8")
    return (
        render_form(groups, base_form_content),
        render_params(groups, base_params_content),
    )


def main() -> int:
    args = parse_args()
    schema_path = Path(args.schema_json)
    output_form_path = Path(args.output_form_yml)
    base_form_path = Path(args.base_form_yml)
    output_params_path = Path(args.output_params_json)
    base_params_path = Path(args.base_params_erb)

    for path in (schema_path, base_form_path, base_params_path):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    output_form_path.parent.mkdir(parents=True, exist_ok=True)
    output_params_path.parent.mkdir(parents=True, exist_ok=True)

    schema = read_json(schema_path)
    form_content, params_content = generate_outputs(
        schema, base_form_path, base_params_path
    )
    output_form_path.write_text(form_content, encoding="utf-8")
    output_params_path.write_text(params_content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - command line error path
        sys.stderr.write(f"Error: {exc}\n")
        raise SystemExit(1)

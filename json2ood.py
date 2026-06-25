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
    union_enabled_by_default: bool = False


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


def normalize_schema_type(property_type: Any) -> str:
    if isinstance(property_type, list):
        property_type = next((item for item in property_type if item != "null"), "")
    return str(property_type).strip().lower()


def detect_scalar_or_false_union(
    property_schema: dict[str, Any],
) -> tuple[str, SchemaValue, bool] | None:
    property_types = property_schema.get("type", "")
    if not isinstance(property_types, list):
        return None

    normalized_types = {
        str(item).strip().lower()
        for item in property_types
        if str(item).strip().lower() != "null"
    }
    scalar_type = next(
        (item for item in ("integer", "number", "string") if item in normalized_types),
        None,
    )
    if scalar_type is None or "boolean" not in normalized_types:
        return None

    any_of = property_schema.get("anyOf")
    if not isinstance(any_of, list):
        return None

    scalar_default: SchemaValue = None
    scalar_format = str(property_schema.get("format", "")).strip().lower()
    has_false_branch = False

    for branch in any_of:
        branch_type = normalize_schema_type(branch.get("type", ""))
        if branch_type == scalar_type:
            if "default" in branch:
                scalar_default = branch.get("default")
            branch_format = str(branch.get("format", "")).strip().lower()
            if branch_format:
                scalar_format = branch_format
        elif branch_type == "boolean" and branch.get("const") is False:
            has_false_branch = True

    if not has_false_branch:
        return None

    top_default = property_schema.get("default")
    value_default = scalar_default
    if scalar_type in {"integer", "number"}:
        if isinstance(top_default, (int, float)) and not isinstance(top_default, bool):
            value_default = top_default
        widget_type = "number_field_or_false"
    else:
        if isinstance(top_default, str) and top_default != "":
            value_default = top_default
        widget_type = (
            "path_selector_or_false" if scalar_format in PATH_FORMATS else "text_field_or_false"
        )

    union_enabled_by_default = False
    if top_default is False:
        union_enabled_by_default = False
    elif value_default not in (None, ""):
        union_enabled_by_default = True

    return widget_type, value_default, union_enabled_by_default


def infer_widget_type(property_schema: dict[str, Any]) -> str | None:
    union_spec = detect_scalar_or_false_union(property_schema)
    if union_spec is not None:
        return union_spec[0]

    property_type = normalize_schema_type(property_schema.get("type", ""))
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

    widget_type = infer_widget_type(property_schema)
    default_value = property_schema.get("default")
    union_enabled_by_default = False

    union_spec = detect_scalar_or_false_union(property_schema)
    if union_spec is not None:
        widget_type, default_value, union_enabled_by_default = union_spec

    return FieldSpec(
        original_name=property_name,
        normalized_name=normalize_key(property_name),
        label=str(property_schema.get("title") or property_name),
        help_text=first_line(property_schema.get("description")),
        widget_type=widget_type,
        required=property_name in required_fields,
        default_value=default_value,
        enum_values=tuple(property_schema.get("enum", ())),
        union_enabled_by_default=union_enabled_by_default,
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


def rendered_field_names(field_spec: FieldSpec) -> list[str]:
    if field_spec.widget_type and field_spec.widget_type.endswith("_or_false"):
        return [f"{field_spec.normalized_name}_enabled", field_spec.normalized_name]
    return [field_spec.normalized_name]


def render_group(group: GroupSpec) -> list[str]:
    lines = [
        f"  {group.normalized_name}:",
        f"    label: {yaml_single_quote(group.label)}",
        "    widget: 'check_box'",
        "    html_options:",
        "      data:",
    ]

    for field_spec in group.fields:
        for field_name in rendered_field_names(field_spec):
            lines.append(f"        hide-{field_name}-when-un-checked: true")

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


def render_scalar_field(
    field_name: str,
    label: str,
    widget_type: str | None,
    required: bool,
    default_value: SchemaValue,
    enum_values: tuple[SchemaValue, ...],
    help_text: str,
) -> list[str]:
    lines = [
        f"  {field_name}:",
        f"    label: {yaml_single_quote(label)}",
    ]

    if required:
        lines.append("    required: true")

    if widget_type == "check_box":
        # Render booleans as a two-option select so the OOD form picks up
        # data-hide-...-when-un-checked rules consistently. The default option
        # is listed first so OOD treats it as the initial selection.
        lines.append("    widget: select")
        is_default_true = default_value is True
        default_str = "true" if is_default_true else "false"
        other_str = "false" if is_default_true else "true"
        lines.append("    options:")
        lines.append(f"      - ['{default_str}', '{default_str}']")
        lines.append(f"      - ['{other_str}', '{other_str}']")
        if isinstance(default_value, bool):
            lines.append(f"    value: {default_str}")
    elif widget_type == "text_field":
        lines.append("    widget: text_field")
        if default_value not in (None, ""):
            lines.append(f"    value: {yaml_single_quote(default_value)}")
    elif widget_type == "path_selector":
        lines.append("    widget: path_selector")
        if default_value not in (None, ""):
            lines.append(f"    value: {yaml_single_quote(default_value)}")
        lines.append(
            "    directory: \"<%= ENV.fetch('NF2OOD_DEFAULT_DIRECTORY', ENV.fetch('HOME', '/')) %>\""
        )
        lines.append("    favorites:")
        lines.append("      - \"<%= ENV.fetch('HOME', '/') %>\"")
    elif widget_type == "number_field":
        lines.append("    widget: number_field")
        # bool is a subclass of int in Python, so an explicit bool check is
        # needed to keep "value: True" / "value: False" from leaking into the
        # YAML when a schema (unusually) types a flag as a number with a
        # boolean default.
        if (
            isinstance(default_value, (int, float))
            and not isinstance(default_value, bool)
        ):
            lines.append(f"    value: {default_value}")
        lines.append("    step: 1")
    elif widget_type == "select":
        lines.append("    widget: select")
        lines.extend(render_select_options(default_value, enum_values))

    if help_text:
        lines.append(f"    help: {yaml_single_quote(help_text)}")

    lines.append("")
    return lines


def render_union_field(field_spec: FieldSpec) -> list[str]:
    base_widget_type = field_spec.widget_type[: -len("_or_false")]
    controller_name = f"{field_spec.normalized_name}_enabled"
    lines = [
        f"  {controller_name}:",
        f"    label: {yaml_single_quote(f'Enable {field_spec.label}')}",
        "    widget: select",
        "    options:",
        f"      - ['Disabled', 'false', data-hide-{field_spec.normalized_name}: true]",
        "      - ['Enabled', 'true']",
        f"    value: {yaml_single_quote('true' if field_spec.union_enabled_by_default else 'false')}",
        "",
    ]
    lines.extend(
        render_scalar_field(
            field_name=field_spec.normalized_name,
            label=field_spec.label,
            widget_type=base_widget_type,
            required=field_spec.required,
            default_value=field_spec.default_value,
            enum_values=field_spec.enum_values,
            help_text=field_spec.help_text,
        )
    )
    return lines


def render_field(field_spec: FieldSpec) -> list[str]:
    if field_spec.widget_type and field_spec.widget_type.endswith("_or_false"):
        return render_union_field(field_spec)

    return render_scalar_field(
        field_name=field_spec.normalized_name,
        label=field_spec.label,
        widget_type=field_spec.widget_type,
        required=field_spec.required,
        default_value=field_spec.default_value,
        enum_values=field_spec.enum_values,
        help_text=field_spec.help_text,
    )


def render_form(groups: list[GroupSpec], base_form_content: str) -> str:
    lines = [base_form_content.rstrip(), "", ""]
    field_order = [*STATIC_FORM_FIELDS]

    for group in groups:
        lines.extend(render_group(group))
        field_order.append(group.normalized_name)
        for field_spec in group.fields:
            lines.extend(render_field(field_spec))
            field_order.extend(rendered_field_names(field_spec))

    lines.append("form:")
    lines.extend(f"  - {field_name}" for field_name in field_order)
    lines.extend(f"  - {field_name}" for field_name in TRAILING_FORM_FIELDS)
    lines.append("")
    return "\n".join(lines)


def render_params_entry(field_spec: FieldSpec) -> str:
    if field_spec.widget_type and field_spec.widget_type.endswith("_or_false"):
        controller_name = f"{field_spec.normalized_name}_enabled"
        if field_spec.widget_type.startswith("number_field"):
            value_expression = f"to_number.call(context.{field_spec.normalized_name})"
        else:
            value_expression = f"context.{field_spec.normalized_name}"
        return (
            f'    "{field_spec.original_name}": '
            f"false_if_disabled.call(context.{controller_name}, {value_expression})"
        )

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

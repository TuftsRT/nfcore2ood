#!/usr/bin/env python3

"""Apply build-time __TOKEN__ substitutions to a generated OOD app directory.

Replaces the per-file ``perl -0pi -e`` loop in ``nf2ood``: one Python process
walks the small set of files in the app dir that contain ``__TOKEN__``
placeholders and applies every substitution in a single read/write pass per
file.

Usage::

    customize_app.py <app_dir>
        --set __PIPELINE_NAME__=nf-core-rnaseq
        --set __PIPELINE_VERSION__=3.18.0
        [--remove-banner]

``--set`` is repeatable; each value is split on the first ``=``. ``--remove-
banner`` deletes the ``<!-- NF2OOD_BANNER_START -->...<!-- NF2OOD_BANNER_END -->``
block in ``form.yml.erb`` (used when no header image URL is available).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Files in the generated app dir that may contain __TOKEN__ placeholders.
# Listed explicitly (rather than walking the tree) so binary assets such as
# icon.png are never opened as text.
SUBSTITUTION_TARGETS = (
    "form.yml.erb",
    "manifest.yml",
    "submit.yml.erb",
    "template/script.sh.erb",
    "README.md",
)

BANNER_BLOCK_PATTERN = re.compile(
    r"\n  <!-- NF2OOD_BANNER_START -->.*?<!-- NF2OOD_BANNER_END -->\n",
    re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app_dir", help="Generated OOD app directory")
    parser.add_argument(
        "--set",
        dest="substitutions",
        action="append",
        default=[],
        metavar="TOKEN=VALUE",
        help="Replace TOKEN with VALUE everywhere in the target files (repeatable).",
    )
    parser.add_argument(
        "--remove-banner",
        action="store_true",
        help="Remove the NF2OOD_BANNER_START/END block from form.yml.erb.",
    )
    return parser.parse_args()


def parse_substitutions(items: list[str]) -> dict[str, str]:
    subs: dict[str, str] = {}
    for raw in items:
        if "=" not in raw:
            raise SystemExit(
                f"customize_app: invalid --set value '{raw}' (expected TOKEN=VALUE)"
            )
        token, value = raw.split("=", 1)
        subs[token] = value
    return subs


def apply_substitutions(
    path: Path, subs: dict[str, str], remove_banner: bool
) -> None:
    if not path.is_file():
        return

    original = path.read_text(encoding="utf-8")
    content = original

    if remove_banner and path.name == "form.yml.erb":
        content = BANNER_BLOCK_PATTERN.sub("", content)

    for token, value in subs.items():
        content = content.replace(token, value)

    # YAML expects lowercase booleans. json2ood.py emits them lowercase, but
    # certain code paths can still produce Python-style True/False; normalise
    # only in form.yml.erb to keep the rest of the file content untouched.
    if path.name == "form.yml.erb":
        content = content.replace("value: True", "value: true")
        content = content.replace("value: False", "value: false")

    if content != original:
        path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        raise SystemExit(f"customize_app: app dir not found: {app_dir}")

    subs = parse_substitutions(args.substitutions)
    for relative in SUBSTITUTION_TARGETS:
        apply_substitutions(app_dir / relative, subs, args.remove_banner)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        sys.stderr.write(f"customize_app: error: {exc}\n")
        raise SystemExit(1)

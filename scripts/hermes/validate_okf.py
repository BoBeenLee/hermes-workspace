#!/usr/bin/env python3
"""Validate the Hermes Workspace OKF knowledge bundle."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "knowledge"
REQUIRED_FIELDS = {
    "type",
    "title",
    "description",
    "resource",
    "tags",
    "timestamp",
}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    raw = text[4:end]
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.startswith(" "):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, text[end + len("\n---\n") :]


def validate() -> list[str]:
    errors: list[str] = []

    if not KNOWLEDGE.is_dir():
        return ["knowledge/ directory is missing"]

    root_index = KNOWLEDGE / "index.md"
    if not root_index.is_file():
        errors.append("knowledge/index.md is missing")
    else:
        parsed = parse_frontmatter(root_index)
        if parsed is None:
            errors.append("knowledge/index.md must declare okf_version frontmatter")
        elif parsed[0].get("okf_version", "").strip('"') != "0.1":
            errors.append('knowledge/index.md must contain okf_version: "0.1"')

    if not (KNOWLEDGE / "log.md").is_file():
        errors.append("knowledge/log.md is missing")

    for path in sorted(KNOWLEDGE.rglob("*.md")):
        rel = path.relative_to(ROOT)
        if path == root_index or path.name == "log.md":
            continue

        if path.name == "index.md":
            if parse_frontmatter(path) is not None:
                errors.append(f"{rel} must be a plain table of contents without frontmatter")
            continue

        parsed = parse_frontmatter(path)
        if parsed is None:
            errors.append(f"{rel} is missing YAML frontmatter")
            continue
        fields, body = parsed
        missing = sorted(REQUIRED_FIELDS - set(fields))
        if missing:
            errors.append(f"{rel} missing required frontmatter fields: {', '.join(missing)}")
        if not fields.get("resource", "").startswith("repo://hermes-workspace/knowledge/"):
            errors.append(f"{rel} resource must use repo://hermes-workspace/knowledge/")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", fields.get("timestamp", "")):
            errors.append(f"{rel} timestamp must be ISO-8601 with numeric timezone")
        if not body.lstrip().startswith("# "):
            errors.append(f"{rel} body must start with an H1 heading after frontmatter")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"OKF validation error: {error}", file=sys.stderr)
        return 1
    print("OKF validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

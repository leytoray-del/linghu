#!/usr/bin/env python3
"""Merge email settings into the service's environment file.

    python3 merge_env.py <settings file> <environment file>

The settings file holds KEY=VALUE lines. Only ERF_MAIL_* and ERF_SMTP_* keys are accepted, so this
cannot be used to change anything else. An empty value removes the key. Values are written in single
quotes, which systemd's EnvironmentFile and a shell both read literally; a value therefore must not
contain a single quote or a line break.
"""

from __future__ import annotations

import re
import sys

KEY = re.compile(r"ERF_(MAIL|SMTP)_[A-Z_]+")


def read_updates(path: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not KEY.fullmatch(key):
                sys.exit(f"Refusing to set {key}: only ERF_MAIL_* and ERF_SMTP_* settings can be changed here.")
            if "'" in value:
                sys.exit(f"The value for {key} must not contain a single quote.")
            updates[key] = value
    return updates


def merge(lines: list[str], updates: dict[str, str]) -> list[str]:
    kept = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    return kept + [f"{key}='{value}'" for key, value in updates.items() if value != ""]


def main() -> None:
    settings_file, env_file = sys.argv[1], sys.argv[2]
    updates = read_updates(settings_file)
    with open(env_file, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    with open(env_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(merge(lines, updates)) + "\n")
    changed = sorted(k for k, v in updates.items() if v)
    removed = sorted(k for k, v in updates.items() if not v)
    print("Email settings updated: " + ", ".join(changed) + (f"; removed: {', '.join(removed)}" if removed else ""))


if __name__ == "__main__":
    main()

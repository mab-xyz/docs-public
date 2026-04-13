#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CurlExample:
    title: str
    command: str


def extract_curl_commands(markdown: str) -> list[CurlExample]:
    examples: list[CurlExample] = []
    heading_stack: dict[int, str] = {}
    in_shell_fence = False
    fence_lines: list[str] = []

    for line in markdown.splitlines():
        stripped = line.strip()

        if in_shell_fence:
            if stripped == "```":
                block = "\n".join(fence_lines).strip()
                sections = [
                    section.strip()
                    for section in re.split(r"\n\s*\n", block)
                    if section.strip()
                ]
                title = heading_stack.get(3) or heading_stack.get(2) or heading_stack.get(1) or "Untitled example"
                for section in sections:
                    if section.lstrip().startswith("curl "):
                        examples.append(CurlExample(title=title, command=section))
                fence_lines = []
                in_shell_fence = False
            else:
                fence_lines.append(line)
            continue

        if stripped.startswith("```") and stripped[3:].strip().lower() in {"bash", "sh", "shell"}:
            in_shell_fence = True
            fence_lines = []
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            heading_stack[level] = title
            for deeper_level in tuple(key for key in heading_stack if key > level):
                del heading_stack[deeper_level]

    return examples


def inject_api_key(command: str, api_key: str | None) -> str:
    if not api_key:
        return command
    return command.replace("YOUR_API_KEY", api_key).replace("$MAB_API_KEY", api_key)


def redact_api_key(command: str, api_key: str | None) -> str:
    if not api_key:
        return command
    return command.replace(api_key, "***REDACTED***")


def run_command(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract curl commands from a markdown file and run them."
    )
    parser.add_argument(
        "markdown_file",
        nargs="?",
        default="api.mab.xyz.md",
        help="Markdown file to scan (default: api.mab.xyz.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted curl commands without executing them.",
    )
    args = parser.parse_args()

    markdown_path = Path(args.markdown_file)
    if not markdown_path.is_file():
        print(f"error: file not found: {markdown_path}", file=sys.stderr)
        return 1

    examples = extract_curl_commands(markdown_path.read_text(encoding="utf-8"))
    if not examples:
        print(f"error: no curl commands found in {markdown_path}", file=sys.stderr)
        return 1

    api_key = os.environ.get("MAB_API_KEY") or os.environ.get("API_KEY")

    for index, example in enumerate(examples, start=1):
        command = inject_api_key(example.command, api_key)
        display_command = redact_api_key(command, api_key)
        print(f"=== example {index}/{len(examples)}: {example.title} ===")
        print(display_command)
        print()

        if args.dry_run:
            continue

        result = run_command(command)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
        print(f"[exit_code={result.returncode}]")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# PostToolUse — keep edits CI-green: auto ruff-format + ruff --fix the just-edited Python file.
# Mirrors the project gate (root CLAUDE.md). Receives the hook payload as JSON on stdin.
f="$(python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get("tool_input") or {}).get("file_path", "") or "")' 2>/dev/null)"
case "$f" in
  *.py)
    uv run --no-sync ruff format -- "$f" >/dev/null 2>&1 || true
    uv run --no-sync ruff check --fix -- "$f" >/dev/null 2>&1 || true
    ;;
esac
exit 0

#!/usr/bin/env bash
# PreToolUse guard — block edits/writes to secrets files (Small Cuts no-secrets policy).
# Receives the hook payload as JSON on stdin; exit code 2 blocks the tool and shows stderr.
f="$(python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get("tool_input") or {}).get("file_path", "") or "")' 2>/dev/null)"
b="$(basename -- "$f" 2>/dev/null)"
case "$b" in
  .env | .env.* | *.env | op-connect.env | op-service-account.env | *.pem | *.key | .npmrc)
    echo "🚫 Blocked edit to '$f' — that looks like a secrets file. Small Cuts keeps secrets in 1Password Connect, never in the repo (gitleaks would also fail CI)." >&2
    exit 2
    ;;
esac
exit 0

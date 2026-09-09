#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap: Longbridge CLI + skills.
set -euo pipefail

export PATH="/usr/local/bin:${HOME}/.local/bin:${PATH}"

if ! command -v longbridge >/dev/null 2>&1; then
  curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh
fi

if command -v longbridge >/dev/null 2>&1; then
  longbridge update || true
fi

SKILLS_SRC="/workspace/.cursor/skills"
if [ -d "${SKILLS_SRC}" ]; then
  mkdir -p "${HOME}/.cursor/skills" "${HOME}/.agents/skills"
  cp -a "${SKILLS_SRC}/." "${HOME}/.cursor/skills/"
  cp -a "${SKILLS_SRC}/." "${HOME}/.agents/skills/"
fi

# QuantHarness Python env (TA-Lib manylinux wheel; no extra C compile on boot)
VENV="${HOME}/.venvs/quantharness"
REQ="/workspace/third_party/QuantHarness/requirements.txt"
if [ -f "${REQ}" ]; then
  if [ ! -x "${VENV}/bin/python" ]; then
    python3 -m venv "${VENV}"
  fi
  if ! "${VENV}/bin/python" -c "import talib, langgraph" >/dev/null 2>&1; then
    "${VENV}/bin/pip" install -U pip wheel
    "${VENV}/bin/pip" install -r "${REQ}"
  fi
fi

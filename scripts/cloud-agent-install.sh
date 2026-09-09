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

#!/usr/bin/env bash
# Setup / check helper. Futu 模拟盘 auto-trade start/stop is a Windows scheduled task.
# On Windows Git Bash this calls scripts/quant-control.ps1.
# On Mac/Linux it only installs the Python venv — OpenD fills will not work here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
ACTION="${1:-help}"

windows_ps() {
  local act="$1"
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\\quant-control.ps1" "${act}"
    return $?
  fi
  echo "OpenD 模拟盘 must run on a Windows PC with 牛牛 + OpenD."
  echo "Copy this folder there and double-click quant.cmd"
  echo "模擬盤必須在有牛牛與 OpenD 的 Windows 電腦上跑。請在那台電腦雙擊 quant.cmd"
  return 1
}

setup_unix() {
  PY="${ROOT}/.venv/bin/python"
  if [ ! -x "${PY}" ]; then
    python3 -m venv "${ROOT}/.venv"
  fi
  "${ROOT}/.venv/bin/pip" install -U pip wheel
  "${ROOT}/.venv/bin/pip" install -r "${ROOT}/requirements-quant-loop.txt"
  echo "venv ready. Longbridge: curl -sSL https://open.longbridge.com/longbridge/longbridge-terminal/install | sh"
  echo "This machine still cannot place Futu 模拟盘 unless OpenD is listening on 127.0.0.1:11111."
}

case "${ACTION}" in
  setup)
    if command -v powershell.exe >/dev/null 2>&1; then
      windows_ps setup
    else
      setup_unix
    fi
    ;;
  start|stop|status|check|login)
    windows_ps "${ACTION}"
    ;;
  help|*)
    cat <<'EOF'
Quant helper

Windows (recommended for 模拟盘):
  Double-click quant.cmd
  or:  bash scripts/quant-control.sh setup|start|stop|status|check|login

Mac/Linux:
  bash scripts/quant-control.sh setup
  Auto-trade start/stop needs the Windows PC that runs Futu OpenD.
EOF
    ;;
esac

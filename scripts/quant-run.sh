#!/usr/bin/env bash
# One command for Cursor Automations: ensure a tiny TA-Lib venv, then loop + dry-run executor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
export PATH="/usr/local/bin:${HOME}/.local/bin:${PATH}"
export LD_LIBRARY_PATH="${HOME}/.local/lib:${LD_LIBRARY_PATH:-}"

VENV="${HOME}/.venvs/quant-loop"
REQ="${ROOT}/requirements-quant-loop.txt"

python_ok() {
  local bin="$1"
  [ -x "${bin}" ] && "${bin}" -c "import talib, pandas" >/dev/null 2>&1
}

PY=""
for candidate in "${ROOT}/.venv/bin/python" "${HOME}/.venvs/quantharness/bin/python" "${VENV}/bin/python"; do
  if python_ok "${candidate}"; then
    PY="${candidate}"
    break
  fi
done

if [ -z "${PY}" ]; then
  python3 -m venv "${VENV}"
  "${VENV}/bin/pip" install -U pip wheel >/dev/null
  "${VENV}/bin/pip" install -r "${REQ}"
  PY="${VENV}/bin/python"
fi

echo "python ${PY}"
"${PY}" -m analysis.loop
"${PY}" -m analysis.executor

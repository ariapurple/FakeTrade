#!/usr/bin/env bash
# One command for Cursor Automations: TA-Lib venv, watchlist loop, Futu 模拟盘 executor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
export PATH="/usr/local/bin:${HOME}/.local/bin:${PATH}"
export LD_LIBRARY_PATH="${HOME}/.local/lib:${LD_LIBRARY_PATH:-}"

VENV="${HOME}/.venvs/quant-loop"
REQ="${ROOT}/requirements-quant-loop.txt"

python_ok() {
  local bin="$1"
  [ -x "${bin}" ] && "${bin}" -c "import talib, pandas, futu" >/dev/null 2>&1
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
if ! "${PY}" -c "from analysis.session import in_us_trade_window; raise SystemExit(0 if in_us_trade_window() else 1)"; then
  echo "outside Futu US sessions (closed Sat 04:00-Sun 20:00 ET); skip"
  exit 0
fi
"${PY}" -m analysis.loop
if ! "${PY}" -c "from analysis.session import in_us_rth; raise SystemExit(0 if in_us_rth() else 1)"; then
  echo "outside US regular hours (09:30-16:00 ET); signals only, no 模拟盘"
  exit 0
fi
"${PY}" -c "from analysis.hourly import run_book_executors; raise SystemExit(run_book_executors())"

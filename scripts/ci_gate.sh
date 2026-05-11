#!/usr/bin/env bash

set -euo pipefail

if [ -x "./.venv/bin/python" ]; then
  PYTHON_BIN="./.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python/python3 not found in PATH" >&2
  exit 127
fi

run_python() {
  "$PYTHON_BIN" "$@"
}

run_python_module() {
  "$PYTHON_BIN" -m "$@"
}

syntax_check() {
  echo "==> backend-gate: Python syntax check"
  run_python -m py_compile main.py src/config.py src/auth.py src/analyzer.py src/notification.py
  run_python -m py_compile src/storage.py src/scheduler.py src/search_service.py
  run_python -m py_compile src/market_analyzer.py src/stock_analyzer.py
  run_python -m py_compile data_provider/*.py
}

flake8_checks() {
  echo "==> backend-gate: flake8 critical checks"
  if command -v flake8 >/dev/null 2>&1; then
    flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    return
  fi
  run_python_module flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
}

deterministic_checks() {
  echo "==> backend-gate: local deterministic checks"
  ./scripts/test.sh code
  ./scripts/test.sh yfinance
}

offline_test_suite() {
  echo "==> backend-gate: offline test suite"
  run_python_module pytest -m "not network"
}

run_all() {
  syntax_check
  flake8_checks
  deterministic_checks
  offline_test_suite
  echo "==> backend-gate: all checks passed"
}

phase="${1:-all}"

case "$phase" in
  all)
    run_all
    ;;
  syntax)
    syntax_check
    ;;
  flake8)
    flake8_checks
    ;;
  deterministic)
    deterministic_checks
    ;;
  offline-tests)
    offline_test_suite
    ;;
  *)
    echo "Usage: $0 [all|syntax|flake8|deterministic|offline-tests]" >&2
    exit 2
    ;;
esac

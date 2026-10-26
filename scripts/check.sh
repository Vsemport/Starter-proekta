#!/usr/bin/env bash
# Единая точка проверок проекта: тесты, линтер, типы, сборка.
# Её запускают хуки, субагенты, скил /release и CI. Стек определяется по файлам;
# нестандартные команды допиши в блок «Свои команды» и в docs/stack.md.
# Код выхода: 0 — все проверки прошли (или проверок нет), 1 — есть ошибки.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# На macOS системная временная папка лежит по символической ссылке (/var → /private/var);
# часть тестов отвергает такие пути. Даём тестам путь без ссылок.
export TMPDIR
TMPDIR=$(python3 -c 'import os, tempfile; print(os.path.realpath(tempfile.gettempdir()))' 2>/dev/null || echo "${TMPDIR:-/tmp}")

FAIL=0
RAN=0
run() {
  local name="$1"; shift
  RAN=1
  printf '\n== %s ==\n' "$name"
  if "$@"; then printf -- '-- OK: %s\n' "$name"; else printf -- '-- ОШИБКА: %s\n' "$name"; FAIL=1; fi
}
has_npm_script() {
  python3 - "$1" <<'PY'
import json, sys
try:
    scripts = json.load(open('package.json', encoding='utf-8')).get('scripts', {})
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if sys.argv[1] in scripts else 1)
PY
}

# --- JavaScript / TypeScript ---
if [ -f package.json ]; then
  PM=npm
  [ -f pnpm-lock.yaml ] && PM=pnpm
  [ -f yarn.lock ] && PM=yarn
  [ -f bun.lockb ] && PM=bun
  for s in lint typecheck test build; do
    has_npm_script "$s" && run "$PM run $s" "$PM" run "$s"
  done
fi

# --- Python ---
if [ -f pyproject.toml ] || [ -f requirements.txt ] || [ -f setup.py ] || ls tests/test_*.py >/dev/null 2>&1; then
  command -v ruff >/dev/null 2>&1 && run "ruff check" ruff check .
  if command -v pytest >/dev/null 2>&1 && { [ -d tests ] || ls test_*.py >/dev/null 2>&1; }; then
    run "pytest" pytest -q
  elif ls tests/test_*.py >/dev/null 2>&1; then
    run "unittest" python3 -m unittest discover -s tests -p 'test_*.py'
  fi
fi

# --- Go ---
if [ -f go.mod ] && command -v go >/dev/null 2>&1; then
  run "go vet" go vet ./...
  run "go test" go test ./...
fi

# --- Rust ---
if [ -f Cargo.toml ] && command -v cargo >/dev/null 2>&1; then
  run "cargo check" cargo check
  run "cargo test" cargo test
fi

# --- Свои команды (см. docs/stack.md) ---
# run "мой линтер" bash -c 'команда'

if [ "$RAN" = 0 ]; then
  echo "Проверок не настроено: нет package.json со scripts lint/typecheck/test/build, pyproject.toml, requirements.txt, tests/test_*.py, go.mod или Cargo.toml."
  echo "Опиши команды проверок в docs/stack.md и добавь их в блок «Свои команды» этого файла."
  exit 0
fi

printf '\n== ИТОГ: %s ==\n' "$([ "$FAIL" = 0 ] && echo 'все проверки прошли' || echo 'есть ошибки')"
exit "$FAIL"

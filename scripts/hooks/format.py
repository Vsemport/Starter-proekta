#!/usr/bin/env python3
"""PostToolUse-хук для Edit/Write/MultiEdit: форматирует изменённый файл кода, если в проекте есть форматтер.

Ничего не блокирует и не устанавливает. Нет форматтера — молчит. Файлы вне проекта,
документацию (.md), .business/, .claude/, node_modules и сборки не трогает.
"""
import json
import os
import shutil
import subprocess
import sys

SKIP_DIRS = {'node_modules', '.git', '.business', '.claude', 'dist', 'build', 'out', '.next', 'coverage', 'vendor'}
SKIP_FILES = {'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock'}
PRETTIER_EXT = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json', '.css', '.scss', '.html', '.vue', '.svelte', '.yaml', '.yml'}


def formatter_for(root, path):
    ext = os.path.splitext(path)[1].lower()
    if ext in PRETTIER_EXT:
        local = os.path.join(root, 'node_modules', '.bin', 'prettier')
        tool = local if os.path.isfile(local) else shutil.which('prettier')
        return [tool, '--write', '--log-level', 'warn', path] if tool else None
    if ext == '.py':
        if shutil.which('ruff'):
            return ['ruff', 'format', '--quiet', path]
        if shutil.which('black'):
            return ['black', '--quiet', path]
        return None
    if ext == '.go' and shutil.which('gofmt'):
        return ['gofmt', '-w', path]
    if ext == '.rs' and shutil.which('rustfmt'):
        return ['rustfmt', '--quiet', path]
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    path = data.get('tool_input', {}).get('file_path') or ''
    root = os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd()
    root = os.path.abspath(root)
    path = os.path.abspath(path) if path else ''
    if not path or not path.startswith(root + os.sep) or not os.path.isfile(path):
        return 0
    relative_parts = os.path.relpath(path, root).split(os.sep)
    if any(part in SKIP_DIRS for part in relative_parts[:-1]) or relative_parts[-1] in SKIP_FILES:
        return 0
    command = formatter_for(root, path)
    if not command:
        return 0
    try:
        subprocess.run(command, cwd=root, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

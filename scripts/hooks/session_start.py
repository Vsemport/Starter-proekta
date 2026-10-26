#!/usr/bin/env python3
"""SessionStart-хук: подаёт Claude ориентировку в начале сессии.

Дата и ISO-неделя, ветка и число изменённых файлов, активные планы с последним checkpoint,
файл текущей недели, напоминание о калибровке. Ничего не меняет. Секреты не читает.
"""
import datetime
import glob
import json
import os
import subprocess
import sys

ACTIVE = ('в работе', 'одобрен', 'на ревью', 'заблокирован', 'пауза')
LIMIT = 4000


def git(root, *args):
    try:
        result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def head(path, n):
    try:
        with open(path, encoding='utf-8', errors='ignore') as handle:
            return [line.rstrip() for line in handle.readlines()[:n]]
    except OSError:
        return []


def plan_info(path):
    lines = head(path, 400)
    status = next((line.split(':', 1)[1].strip() for line in lines[:15] if line.lower().startswith('статус:')), '')
    if not any(word in status.lower() for word in ACTIVE):
        return None
    checkpoint = []
    inside = False
    for line in lines:
        if line.startswith('## '):
            if inside:
                break
            inside = line.lower().startswith('## checkpoint')
            continue
        if inside and line.strip():
            checkpoint.append(line.strip())
    return status, checkpoint[:10]


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        data = {}
    root = os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd()
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    out = [f'Сегодня {today.isoformat()}, ISO-неделя {iso_year}-W{iso_week:02d}.']

    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    if branch:
        changed = git(root, 'status', '--porcelain')
        count = len(changed.splitlines()) if changed else 0
        out.append(f'Git: ветка {branch}, изменённых файлов: {count}.')

    plans = []
    for path in glob.glob(os.path.join(root, 'plans', '*.md')):
        if os.path.basename(path) in ('README.md', 'TEMPLATE.md'):
            continue
        info = plan_info(path)
        if info:
            plans.append((os.path.getmtime(path), path, *info))
    plans.sort(reverse=True)
    if plans:
        out.append('Активные планы: ' + '; '.join(f'{os.path.relpath(p, root)} ({s})' for _, p, s, _ in plans) + '.')
        _, path, _, checkpoint = plans[0]
        if checkpoint:
            out.append(f'Последний checkpoint ({os.path.relpath(path, root)}):')
            out.extend('  ' + line for line in checkpoint)
    else:
        out.append('Активных планов в plans/ нет.')

    week_file = os.path.join(root, '.business', 'execution', f'{iso_year}-W{iso_week:02d}.md')
    if os.path.isfile(week_file):
        out.append(f'Файл недели {os.path.relpath(week_file, root)}:')
        out.extend('  ' + line for line in head(week_file, 20) if line.strip())

    stack = os.path.join(root, 'docs', 'stack.md')
    if os.path.isfile(stack) and '[ГГГГ-ММ-ДД]' in '\n'.join(head(stack, 10)):
        out.append('docs/stack.md не заполнен: техническая калибровка не проведена, предложи /calibrate при работе с кодом.')

    text = '\n'.join(out)
    if len(text) > LIMIT:
        text = text[:LIMIT] + '\n…(обрезано)'
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': text}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

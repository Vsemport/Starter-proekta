#!/usr/bin/env python3
"""UserPromptSubmit-хук: добавляет к каждому запросу сегодняшнюю дату, день недели и ISO-неделю.

Нужно, чтобы планы недели, даты в файлах и сроки не придумывались, а брались из системы.
"""
import datetime
import json
import sys

WEEKDAYS = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')


def main():
    try:
        sys.stdin.read()
    except OSError:
        pass
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    text = f'Сегодня {today.isoformat()}, {WEEKDAYS[today.weekday()]}; ISO-неделя {iso_year}-W{iso_week:02d}.'
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': text}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

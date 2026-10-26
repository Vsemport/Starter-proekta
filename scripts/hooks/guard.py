#!/usr/bin/env python3
"""PreToolUse-хук для Bash: объясняет и останавливает необратимое, спрашивает про рискованное.

Читает JSON Claude Code из stdin. Печатает решение в JSON:
  deny — команда не выполняется, причина показывается;
  ask  — Claude Code спросит владельца, показав причину.
Если решения нет — молчит, и команда идёт обычным путём через permissions из settings.json.
При ошибке разбора входа молчит (обычные правила разрешений продолжают действовать).
"""
import json
import re
import sys

SECRET_FILE = r'(?:\.env(?!\.(?:example|sample)\b)(?:\.[\w.-]+)?|[\w./-]*\.pem|[\w./-]*\.key|[\w./-]*credentials\.json|[\w./-]*id_(?:rsa|ed25519)(?!\.pub))'

DENY = [
    (r'\brm\s+(?:-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*\s+(?:-[a-zA-Z]*\s+)*(?:--\s+)?["\']?(?:/|/\*|~|~/|~/\*|\$HOME|\$HOME/\*|\.|\./|\.\.|\*|\.git|\.git/)["\']?(?:\s|$)',
     'Удаление корня диска, домашней папки, текущей папки или .git необратимо. Укажи конкретный путь внутри проекта и объясни, что и зачем удаляем.'),
    (r'\bgit\s+push\b[^|;&]*(?:\s--force\b|\s-f\b)[^|;&]*\b(?:main|master)\b|\bgit\s+push\b[^|;&]*\b(?:main|master)\b[^|;&]*(?:\s--force\b|\s-f\b)',
     'Перезапись истории в main/master ломает работу всех, кто её скачал, и уничтожает коммиты. Если нужно исправить — новый коммит поверх или ветка плана.'),
    (r'\b(?:cat|less|more|head|tail|bat|strings|xxd|base64|open|code|vim|vi|nano|grep\s+-r?\s*["\']?\.|sed)\s+[^|;&]*' + SECRET_FILE + r'(?:\s|$)',
     'Файлы с секретами целиком не читаем: содержимое попадёт в историю разговора. Нужна одна переменная — grep "^ИМЯ=" .env — и не выводи значение в ответ.'),
    (r'(?:\bsource\s+|^\s*\.\s+|\bexport\s+\$\(\s*cat\s+)' + SECRET_FILE,
     'Загрузка .env в окружение раскрывает все секреты последующим командам. Передавай конкретные переменные явно.'),
    (r'\bexport\b[^|;&]*(?:&&|;)\s*(?:curl|wget)\b|\b(?:curl|wget)\b[^|;&]*(?:-d|--data|--data-binary|-F|--form)\s*@?["\']?' + SECRET_FILE,
     'Похоже на отправку переменных окружения или файла с секретами наружу. Такие действия только руками владельца.'),
    (r'\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python3?|node)\b',
     'Запуск скрипта из интернета без просмотра. Сначала скачай в файл, покажи владельцу, потом запускай.'),
    (r'\bchmod\s+(?:-R\s+)?777\b',
     'Права 777 открывают файл всем пользователям системы. Выставь минимально нужные права.'),
]

ASK = [
    (r'\bgit\s+push\b', 'Отправка в удалённый репозиторий. Проверь ветку и что в ней нет секретов и чужих файлов.'),
    (r'\bgit\s+(?:branch\s+-[dD]\b|reset\s+--hard\b|clean\s+-[a-zA-Z]*[fdx]|checkout\s+--\s+\.|restore\s+\.|stash\s+(?:drop|clear)\b)',
     'Команда уничтожает незакоммиченные изменения или ветку. Убедись, что ничего нужного не потеряется.'),
    (r'\brm\s+(?:-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR]', 'Рекурсивное удаление. Проверь путь и что в папке нет нужного.'),
    (r'\bsudo\b', 'Команда с правами администратора меняет систему, а не проект.'),
    (r'\b(?:npm|pnpm|yarn)\s+(?:publish|unpublish)\b|\bdocker\s+(?:push|rm|rmi|system\s+prune)\b|\bgh\s+(?:release|pr\s+merge|repo\s+(?:delete|edit|archive))\b|\b(?:vercel|netlify)\b[^|;&]*(?:--prod|deploy)|\bkubectl\s+(?:delete|apply)\b|\bterraform\s+(?:apply|destroy)\b|\bfly\s+deploy\b',
     'Внешнее действие: публикация, выпуск или изменение рабочего окружения. Нужны отдельные полномочия владельца и план отката.'),
    (r'\b(?:DROP\s+(?:TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE|DELETE\s+FROM)\b', 'Команда меняет или удаляет данные в базе. Нужны резервная копия и подтверждение владельца.'),
    (r'\b(?:curl|wget)\b[^|;&]*(?:-X\s*(?:POST|PUT|PATCH|DELETE)|--data\b|-d\s|--form\b|-F\s|--upload-file\b|-T\s)',
     'Отправка данных на внешний адрес. Владелец должен видеть, что и куда уходит.'),
    (r'(?:^|[;&|]\s*)(?:printenv|env)\s*(?:$|[;&|])', 'Вывод всех переменных окружения может показать секреты. Запроси конкретную переменную.'),
    (r'\b(?:crontab|launchctl|systemctl)\b', 'Изменение системных служб и расписаний действует за пределами проекта.'),
    (r'\b(?:npm|pnpm|yarn)\s+(?:i|install|add)\s+(?:-g|--global)\b|\bbrew\s+install\b|\bpip3?\s+install\b(?![^|;&]*(?:-r\s|--requirement|-e\s|\.))',
     'Установка в систему, а не в проект. Проверь, что это нужно глобально.'),
]


def decide(command):
    for pattern, reason in DENY:
        if re.search(pattern, command, re.IGNORECASE | re.MULTILINE):
            return 'deny', reason
    for pattern, reason in ASK:
        if re.search(pattern, command, re.IGNORECASE | re.MULTILINE):
            return 'ask', reason
    return None, None


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get('tool_input', {}).get('command', '')
        if not isinstance(command, str) or not command:
            return 0
    except (ValueError, AttributeError, OSError):
        return 0
    decision, reason = decide(command)
    if decision:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': decision,
            'permissionDecisionReason': reason,
        }}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

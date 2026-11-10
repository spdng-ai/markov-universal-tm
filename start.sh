#!/usr/bin/env sh
# Запуск приложения: ./start.sh  (доп. аргументы передаются в app.py)
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 app.py "$@"; else exec python app.py "$@"; fi

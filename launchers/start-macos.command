#!/bin/bash
# Лончер для macOS — двойной клик открывает браузер с приложением.
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

# Проверка uv
if ! command -v uv &>/dev/null; then
    osascript -e 'display dialog "uv не найден.\n\nУстановите uv и повторите:\nhttps://docs.astral.sh/uv/getting-started/installation/" buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

# Установить web-зависимости если ещё не установлены
uv pip install -e ".[web]" --quiet 2>/dev/null || true

# Открыть браузер через 4 секунды (пока Streamlit стартует)
(sleep 4 && open "http://localhost:8501") &

echo "========================================"
echo "  График дежурств — http://localhost:8501"
echo "  Для остановки нажмите Ctrl+C"
echo "========================================"

uv run streamlit run app.py \
    --server.headless true \
    --server.port 8501 \
    --browser.gatherUsageStats false

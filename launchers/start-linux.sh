#!/bin/bash
# Лончер для Linux — запустить через двойной клик или ./start-linux.sh
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

# Проверка uv
if ! command -v uv &>/dev/null; then
    echo "[ОШИБКА] uv не найден."
    echo "Установите uv: https://docs.astral.sh/uv/getting-started/installation/"
    read -rp "Нажмите Enter для выхода..."
    exit 1
fi

# Установить web-зависимости если ещё не установлены
uv pip install -e ".[web]" --quiet 2>/dev/null || true

# Открыть браузер через 4 секунды (xdg-open — стандартный способ на Linux)
(sleep 4 && xdg-open "http://localhost:8501" 2>/dev/null || true) &

echo "========================================"
echo "  График дежурств — http://localhost:8501"
echo "  Для остановки нажмите Ctrl+C"
echo "========================================"

uv run streamlit run app.py \
    --server.headless true \
    --server.port 8501 \
    --browser.gatherUsageStats false

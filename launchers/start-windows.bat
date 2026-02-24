@echo off
chcp 65001 >nul
setlocal

:: Перейти в корень проекта (папка выше launchers\)
cd /d "%~dp0.."

echo ========================================
echo   График дежурств
echo ========================================

:: Проверка uv
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] uv не найден.
    echo Установите uv: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

:: Установить web-зависимости
echo Проверка зависимостей...
uv pip install -e ".[web]" --quiet 2>nul

:: Открыть браузер через 4 секунды в фоне
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8501"

echo Запуск на http://localhost:8501
echo Для остановки нажмите Ctrl+C
echo.

uv run streamlit run app.py ^
    --server.headless true ^
    --server.port 8501 ^
    --browser.gatherUsageStats false

pause

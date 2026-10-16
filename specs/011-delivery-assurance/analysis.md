# Анализ macOS gate — 2026-10-13

Источникfailure: CI Main38385340188, jobs115255614485/115255614561,
exit139 в weasyprint/text/ffi.py:_dlopen при AppTest ready result. CI test-all
не готовит native Mac path; local875 тестов прошли с DYLD/homebrew. Официальная
документация WeasyPrint подтверждает необходимость достижимых dylib на macOS.
Scope точный: ci-main.yml, test_delivery_workflows.py, этиSDD docs иgeneratedindex.
DEL-001 дополняет environment readiness, ни один продуктовый контракт не ослабляется.
T006..009 имеют проверяемые исходы. CI остается обязательным; mac smoke+whole matrix
не заменяются statictest, всеhistoricalevidence сохраняются. Не требуется новый
продуктовый выбор: это необходимый repair в рамках поручения внедрить доmain.

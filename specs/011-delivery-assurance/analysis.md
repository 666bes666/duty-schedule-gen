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

## 2026-10-16 — повторный benchmark failure

После паузы Main run38921862578 полностью green, включая installed wheel/container.
Test run38921853888 attempt2 снова failed: standard mean96.0154 vs86.3358 ms
(11.2115%), large141.8143 vs128.5737 ms (10.2980%); AMD vs Intel в machine_info.
Scheduler, benchmark cases и их зависимости не менялись в исходном repair.
DEL-003 уточняется до сравнения на одном runner с remeasurement успешного prior
SHA. Это сохраняет порог и prior-success provenance, исключает смешение hardware
и не использует failed-run как baseline. Planned selectors покрывают happy path,
bootstrap, invalid SHA, subprocess failure, cleanup и отсутствие нового отчёта.
Scope уже включает все выбранные файлы; T010→T011→T012→T013 согласованы.
Новый продуктовый выбор или изменение API не требуются.

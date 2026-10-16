# Анализ до реализации

Проверены constitution, docs/sdd, текущие components/onboarding/config_io/autosave и
контракты018/019. Пользователь отменил отдельное внесение и два способа назначения,
подтвердил копирование всех столбцов с пустым именем/новым ID и autosave invalid draft.
Nullable draft не должен становиться Config с default ролями. История копии не переносится.
Public project/schema не расширяем: новый UI envelope отдельный, legacy строгий import
остаётся. Конфликты записи контролирует прежний bridge, один snapshot содержит base+rows.
Каждый ROSTER ID связан с проверкой; scope точный; непроверенные задачи открыты.
Риски cumulative editor deltas, ID/name fallback и отложенного autosave должны иметь
воспроизводящие tests. Существенных открытых продуктовых решений нет.

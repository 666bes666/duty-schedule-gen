# Общие модели и контракты интеграции

Работа сохраняет имена и списки смен существующего Schedule. Все новые бизнес-типы
в models.py; вычисления нормы — workload.py, календарный IO — calendar.py,
проверка/поиск — scheduler; проект не импортирует Streamlit/API.

## Типы

- CalendarDay(date, kind=working|off|short).
- ProductionCalendar(year, month, days: list[CalendarDay], source, fetched_at,
  verified=True, used_saved=False); полный уникальный набор дат. Методы
  is_working(date), hours(date), off_dates(), short_dates(). Для working 8,
  short 7, off 0; часы дежурств на off — 8. Legacy weekdays fallback verified=False.
- Employee.employee_id: постоянный ID; legacy миграция по уникальному имени;
  sick_leaves: list[VacationPeriod], is_on_sick_leave(date). Смена sick_leave и
  DaySchedule.sick_leave добавляются к отпуску/выходному.
- NormChoice(employee_name, employee_id optional, year, month, mode=adjusted|full).
  Config.norm_choices: list[NormChoice]. Выбор относится к конкретному месяцу.
- RuleApproval(employee_name, employee_id optional, date,
  rule=working_streak|weekly_day_off|individual_workday,
  purpose=coverage|monthly_norm, value: int optional, confirmed_at).
  value фиксирует разрешённую длину серии/часы Р, а не общее разрешение нарушать.
  Config.approvals: list[RuleApproval].
- PinnedAssignment.working_hours: int optional; допустимо только для Р.
  DaySchedule.workday_hours: dict[str,int]; 1..обычные 8/7 для индивидуального Р.
- CarryOverState(employee_name, employee_id optional, last_shift,
  consecutive_working/off/same_shift, as_of optional,
  source=legacy|manual|schedule|xls|new_employee, no_previous_shifts=False).
  Старые поля используются для поиска, но legacy без подтверждённого периода
  не удостоверяет ready; new_employee явно задаёт пустую историю.
- MonthlyTarget(calendar_hours, absence_reduction_hours, adjusted_hours,
  selected_hours, mode). Функция calculate_monthly_targets(config, calendar)
  возвращает dict[name,MonthlyTarget]; assignment_hours(day,name,calendar)
  возвращает единые рабочие часы (Р override или календарные 8/7).
- Config.production_calendar: ProductionCalendar optional.
- Schedule.status=draft|ready|diagnostic, diagnostics:list[ScheduleDiagnostic],
  search_status, revision_id, monthly_targets:dict[name,MonthlyTarget].
  ScheduleDiagnostic(code, detail, employee_name optional, date optional,
  approval_rule optional, value optional). Человеко-читаемая причина отдельно
  от устойчивого code; имя события logging остаётся английским snake_case.

## Публичные функции

calendar.fetch_production_calendar(year,month,saved=None) -> ProductionCalendar;
запрос pre=1, при ошибке допустим только проверенный saved того же периода.
Старый fetch_holidays сохраняется адаптером. Везде предпочитается полный снимок.

scheduler.core.generate_schedule(config,holidays=None) -> Schedule. Старый
holidays:set[date] сохраняется как переходный неполный контекст, не удостоверяет
ready. При явно заданном config.production_calendar используется этот снимок.

scheduler.validation.validate_schedule_result(schedule) -> Schedule: возвращает
копию с заново вычисленными status/diagnostics/targets/carry; не доверяет входному
status. Система экспорта и проект вызывают эту функцию перед выдачей файла.

project.ScheduleProject(config, calendars, revisions, active_revisions,
selected_period) + ScheduleRevision(id,parent_id,schedule,created_at).
project.new_project(config), add_revision(project,schedule), current_schedule,
apply_assignments(project,days), check_current(project), serialize_project,
load_project, ensure_exportable(schedule). Следующий месяц зависит от активной
проверенной предыдущей версии; изменение делает зависимые версии диагностическими.

## Совместимость и честность

Старые YAML, имена/списки смен и /schedule/generate сохраняются через адаптеры;
старый generate возвращает пригодный 200 либо 409 schedule_not_ready. Новый
/schedule/plan возвращает оба статуса с диагностикой. Экспорт версии — отдельные
/export/revision/*, экспорт из Config остаётся через генерацию и общую проверку.
Native 422 сохраняется; неизвестный сотрудник старого ICS остаётся 400 JSON.
Неизвестная история/календарь приводят к диагностике, не к угаданному ready.


from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from duty_schedule.calendar import CalendarError, calendar_for_config, get_all_days
from duty_schedule.models import Schedule, ScheduleDiagnostic, ScheduleType, ShiftType
from duty_schedule.scheduler.rules import (
    ALL_SHIFTS,
    WORKING_SHIFTS,
    approval_for,
    assignment_for,
    carry_for_employee,
    matches_employee,
    normal_streak_limit,
)
from duty_schedule.workload import assignment_hours, calculate_monthly_targets


def validate_schedule_result(schedule: Schedule) -> Schedule:
    result = schedule.model_copy(deep=True)
    config = result.config
    diagnostics: list[ScheduleDiagnostic] = []

    def add(code: str, detail: str, name: str | None = None, day: date | None = None) -> None:
        diagnostics.append(
            ScheduleDiagnostic(code=code, detail=detail, employee_name=name, date=day)
        )

    try:
        calendar = calendar_for_config(config)
    except (CalendarError, ValueError) as exc:
        add("calendar_invalid", str(exc))
        fallback = config.model_copy(update={"production_calendar": None})
        calendar = calendar_for_config(fallback)
    if not calendar.verified:
        add("calendar_unverified", "Нет проверенного производственного календаря нужного месяца")
    result.config.production_calendar = calendar
    try:
        result.monthly_targets = calculate_monthly_targets(config, calendar)
    except ValueError as exc:
        add("norm_choice_invalid", str(exc))
        result.monthly_targets = calculate_monthly_targets(
            config.model_copy(update={"norm_choices": []}), calendar
        )
    expected = get_all_days(config.year, config.month)
    dates = [day.date for day in result.days]
    if dates != expected:
        add("period_incomplete", "График должен содержать все даты месяца один раз по порядку")
    known_names = {employee.name for employee in config.employees}
    if len(known_names) != len(config.employees):
        add("duplicate_employee", "Имена сотрудников должны быть уникальными")
    if len({employee.employee_id for employee in config.employees}) != len(config.employees):
        add("duplicate_employee_id", "Идентификаторы сотрудников должны быть уникальными")
    for choice in config.norm_choices:
        if (choice.year, choice.month) == (config.year, config.month) and not any(
            matches_employee(choice.employee_name, choice.employee_id, employee)
            for employee in config.employees
        ):
            add("norm_employee_unknown", "Выбранная норма относится к неизвестному сотруднику")
    valid_days = [day for day in result.days if day.date in expected]
    for day in valid_days:
        day.is_holiday = not calendar.is_working(day.date)
        counts = Counter(name for shift in ALL_SHIFTS for name in getattr(day, shift.value))
        for name, count in counts.items():
            if name not in known_names:
                add("employee_unknown", "Назначение неизвестного сотрудника", name, day.date)
            if count != 1:
                add(
                    "multiple_assignments",
                    "Более одного состояния сотрудника на дату",
                    name,
                    day.date,
                )
        for name in known_names - counts.keys():
            add("assignment_missing", "Нет состояния сотрудника на дату", name, day.date)
        for required_shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT):
            if not getattr(day, required_shift.value):
                add(
                    "coverage",
                    f"Не покрыта обязательная смена {required_shift.value}",
                    day=day.date,
                )
        for name, hours in day.workday_hours.items():
            if name not in day.workday or not 1 <= hours <= (calendar.hours(day.date) or 8):
                add("workday_hours_invalid", "Некорректные индивидуальные часы Р", name, day.date)
    previous_date = date(config.year, config.month, 1) - timedelta(days=1)
    for employee in config.employees:
        histories = [
            item
            for item in config.carry_over
            if matches_employee(item.employee_name, item.employee_id, employee)
        ]
        carry = carry_for_employee(config, employee)
        if len(histories) > 1:
            add("history_duplicate", "Несколько исходных состояний сотрудника", employee.name)
        if carry is None:
            add("history_missing", "Неизвестна история до начала месяца", employee.name)
        elif carry.as_of != previous_date:
            add(
                "history_stale",
                "История должна относиться к последней дате предыдущего месяца",
                employee.name,
            )
        elif carry.source == "legacy":
            add(
                "history_unverified",
                "Историю необходимо подтвердить или ввести вручную",
                employee.name,
            )
        if carry is not None and not carry.no_previous_shifts:
            if (carry.last_shift in WORKING_SHIFTS) != (carry.consecutive_working > 0):
                add(
                    "history_invalid",
                    "Последняя смена не согласована с рабочей серией",
                    employee.name,
                )
            if carry.last_shift is None and not carry.consecutive_off:
                add(
                    "history_invalid",
                    "Пустая история требует явного подтверждения нового сотрудника",
                    employee.name,
                )
        previous_shift = carry.last_shift if carry else None
        streak = carry.consecutive_working if carry else 0
        actual_hours = 0
        for day in sorted(valid_days, key=lambda item: item.date):
            shift = assignment_for(day, employee.name)
            absent = employee.is_on_vacation(day.date) or employee.is_on_sick_leave(day.date)
            if (employee.name in day.vacation and not employee.is_on_vacation(day.date)) or (
                employee.name in day.sick_leave and not employee.is_on_sick_leave(day.date)
            ):
                add(
                    "unexpected_absence",
                    "Отсутствие не задано в исходных данных",
                    employee.name,
                    day.date,
                )
            if absent and shift not in (ShiftType.VACATION, ShiftType.SICK_LEAVE):
                add(
                    "absence_conflict",
                    "Состояние конфликтует с отпуском или больничным",
                    employee.name,
                    day.date,
                )
            if shift in WORKING_SHIFTS:
                streak += 1
                actual_hours += assignment_hours(day, employee.name, calendar)
                if day.date in employee.unavailable_dates:
                    add(
                        "unavailable_date",
                        "Работа в безусловно недоступную дату",
                        employee.name,
                        day.date,
                    )
                if employee.schedule_type == ScheduleType.FIVE_TWO and not calendar.is_working(
                    day.date
                ):
                    add(
                        "five_two_nonworking",
                        "Работа 5/2 в нерабочую дату календаря",
                        employee.name,
                        day.date,
                    )
                if shift == ShiftType.WORKDAY and not calendar.is_working(day.date):
                    add(
                        "workday_nonworking",
                        "Р допускается только в рабочую дату календаря",
                        employee.name,
                        day.date,
                    )
                if previous_shift == ShiftType.EVENING and shift in (
                    ShiftType.MORNING,
                    ShiftType.WORKDAY,
                ):
                    add(
                        "evening_rest",
                        "Утро или Р сразу после вечерней смены",
                        employee.name,
                        day.date,
                    )
                if (
                    shift in (ShiftType.MORNING, ShiftType.EVENING)
                    and (employee.city.value != "moscow" or not employee.on_duty)
                    or shift == ShiftType.NIGHT
                    and (employee.city.value != "khabarovsk" or not employee.on_duty)
                ):
                    add(
                        "shift_eligibility",
                        "Смена не соответствует городу или роли",
                        employee.name,
                        day.date,
                    )
                if (
                    shift == ShiftType.MORNING
                    and employee.evening_only
                    or (shift == ShiftType.EVENING and employee.morning_only)
                ):
                    add(
                        "shift_restriction",
                        "Смена запрещена персональными настройками",
                        employee.name,
                        day.date,
                    )
                if (
                    shift == ShiftType.WORKDAY
                    and employee.on_duty
                    and (employee.morning_only or employee.evening_only or employee.always_on_duty)
                ):
                    add(
                        "duty_only",
                        "Сотрудник настроен только на дежурные смены",
                        employee.name,
                        day.date,
                    )
                if streak > 7:
                    add(
                        "absolute_streak",
                        "Рабочая серия превышает абсолютный предел 7",
                        employee.name,
                        day.date,
                    )
                elif (
                    streak > normal_streak_limit(employee)
                    and approval_for(config, employee, day.date, "working_streak", streak) is None
                ):
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code="approval_required",
                            detail=f"Необходимо подтвердить рабочую серию {streak}",
                            employee_name=employee.name,
                            date=day.date,
                            approval_rule="working_streak",
                            value=streak,
                        )
                    )
                if (
                    employee.is_day_off_weekly(day.date)
                    and approval_for(config, employee, day.date, "weekly_day_off") is None
                ):
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code="approval_required",
                            detail="Необходимо подтвердить работу в еженедельный выходной",
                            employee_name=employee.name,
                            date=day.date,
                            approval_rule="weekly_day_off",
                        )
                    )
                if shift == ShiftType.WORKDAY and employee.name in day.workday_hours:
                    hours = day.workday_hours[employee.name]
                    if (
                        approval_for(config, employee, day.date, "individual_workday", hours)
                        is None
                    ):
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code="approval_required",
                                detail=f"Необходимо подтвердить Р на {hours} часов",
                                employee_name=employee.name,
                                date=day.date,
                                approval_rule="individual_workday",
                                value=hours,
                            )
                        )
            else:
                streak = 0
            previous_shift = shift
        target = result.monthly_targets[employee.name].selected_hours
        if actual_hours != target:
            add(
                "monthly_hours",
                f"Факт {actual_hours} часов, выбранная норма {target}",
                employee.name,
            )
    pin_keys: set[tuple[date, str]] = set()
    for pin in config.pins:
        if pin.date not in expected:
            continue
        key = (pin.date, pin.employee_name)
        if key in pin_keys:
            add("pin_duplicate", "Несколько ручных назначений на дату", pin.employee_name, pin.date)
        pin_keys.add(key)
        pinned_day = next((day for day in valid_days if day.date == pin.date), None)
        if pinned_day is None or pin.employee_name not in getattr(pinned_day, pin.shift.value):
            add("pinned_assignment", "Ручное назначение не сохранено", pin.employee_name, pin.date)
        elif (
            pin.working_hours is not None
            and pinned_day.workday_hours.get(pin.employee_name) != pin.working_hours
        ):
            add(
                "pinned_hours",
                "Индивидуальные часы ручного Р не сохранены",
                pin.employee_name,
                pin.date,
            )
    if diagnostics and result.search_status in (
        "infeasible",
        "timeout",
        "heuristic_exhausted",
        "solver_unavailable",
        "model_invalid",
    ):
        add(
            "search_" + result.search_status,
            {
                "infeasible": "Полная модель ограничений доказана несовместимой",
                "timeout": "Поиск не нашёл решения за отведённое время; невозможность не доказана",
                "heuristic_exhausted": (
                    "Эвристика не нашла допустимое решение; невозможность не доказана"
                ),
                "solver_unavailable": "Запрошенный решатель недоступен",
                "model_invalid": "Ошибка построения модели решателя",
            }[result.search_status],
        )
    from duty_schedule.scheduler.postprocess.carry_over_calc import compute_carry_over

    result.metadata["carry_over"] = compute_carry_over(
        valid_days, config.employees, initial_history=config.carry_over
    )
    result.metadata["production_working_days"] = sum(calendar.is_working(day) for day in expected)
    result.metadata["production_hours"] = sum(calendar.hours(day) for day in expected)
    result.metadata["working_days_per_employee"] = {
        employee.name: sum(employee.name in day.all_assigned() for day in valid_days)
        for employee in config.employees
    }
    result.metadata["total_mornings"] = sum(len(day.morning) for day in valid_days)
    result.metadata["total_evenings"] = sum(len(day.evening) for day in valid_days)
    result.metadata["total_nights"] = sum(len(day.night) for day in valid_days)
    result.diagnostics = diagnostics
    result.status = "diagnostic" if diagnostics else "ready"
    return result

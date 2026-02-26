"""Экспорт расписания в формат iCalendar (.ics)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, vText

from duty_schedule.models import (
    SHIFT_END,
    SHIFT_NAMES_RU,
    SHIFT_START,
    City,
    DaySchedule,
    Schedule,
    ShiftType,
)

ICS_SHIFTS = [ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY]

CITY_TZ = {
    City.MOSCOW: "Europe/Moscow",
    City.KHABAROVSK: "Asia/Vladivostok",
}

KHABAROVSK_WORKDAY_START = (9, 0)
KHABAROVSK_WORKDAY_END = (18, 0)


def _make_datetime(day: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def _shift_times(shift: ShiftType, day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    sh, sm = SHIFT_START[shift]
    eh, em = SHIFT_END[shift]
    dt_start = _make_datetime(day, sh, sm, tz)

    if shift == ShiftType.EVENING:
        dt_end = _make_datetime(day + timedelta(days=1), eh, em, tz)
    else:
        dt_end = _make_datetime(day, eh, em, tz)

    return dt_start, dt_end


def _make_calendar(shift: ShiftType) -> Calendar:
    cal = Calendar()
    cal.add("PRODID", "-//Duty Schedule Generator//RU")
    cal.add("VERSION", "2.0")
    cal.add("X-WR-CALNAME", f"Дежурства: {SHIFT_NAMES_RU[shift]}")
    cal.add("CALSCALE", "GREGORIAN")
    cal.add("METHOD", "PUBLISH")
    return cal


def _employees_on_shift(day: DaySchedule, shift: ShiftType) -> list[str]:
    return {
        ShiftType.MORNING: day.morning,
        ShiftType.EVENING: day.evening,
        ShiftType.NIGHT: day.night,
        ShiftType.WORKDAY: day.workday,
    }[shift]


def export_ics(schedule: Schedule, output_dir: Path) -> list[Path]:
    """
    Сгенерировать отдельный ICS-файл для каждого типа смены.

    Хабаровские сотрудники в workday получают события в Asia/Vladivostok.
    Московские — в Europe/Moscow.

    Returns:
        Список путей к созданным файлам.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    msk_tz = ZoneInfo(schedule.config.timezone)
    khb_tz = ZoneInfo(CITY_TZ[City.KHABAROVSK])
    year = schedule.config.year
    month = schedule.config.month

    employee_city = {emp.name: emp.city for emp in schedule.config.employees}

    calendars: dict[ShiftType, Calendar] = {s: _make_calendar(s) for s in ICS_SHIFTS}

    for day in schedule.days:
        for shift in ICS_SHIFTS:
            names = _employees_on_shift(day, shift)
            if not names:
                continue

            for name in names:
                if shift == ShiftType.WORKDAY and employee_city.get(name) == City.KHABAROVSK:
                    sh, sm = KHABAROVSK_WORKDAY_START
                    eh, em = KHABAROVSK_WORKDAY_END
                    dt_start = _make_datetime(day.date, sh, sm, khb_tz)
                    dt_end = _make_datetime(day.date, eh, em, khb_tz)
                    tz_label = CITY_TZ[City.KHABAROVSK]
                else:
                    dt_start, dt_end = _shift_times(shift, day.date, msk_tz)
                    tz_label = schedule.config.timezone

                event = Event()
                event.add("SUMMARY", vText(f"Дежурство: {SHIFT_NAMES_RU[shift]} — {name}"))
                event.add("DTSTART", dt_start)
                event.add("DTEND", dt_end)
                event.add(
                    "DESCRIPTION",
                    vText(
                        f"Смена: {SHIFT_NAMES_RU[shift]}\n"
                        f"Часовой пояс: {tz_label}\n"
                        f"Все на смене: {', '.join(names)}"
                    ),
                )
                event.add(
                    "UID",
                    vText(
                        f"{year}{month:02d}{day.date.day:02d}-{shift.value}-{name}@duty-schedule"
                    ),
                )
                calendars[shift].add_component(event)

    output_files: list[Path] = []
    shift_filenames = {
        ShiftType.MORNING: "morning.ics",
        ShiftType.EVENING: "evening.ics",
        ShiftType.NIGHT: "night.ics",
        ShiftType.WORKDAY: "workday.ics",
    }

    for shift, cal in calendars.items():
        path = output_dir / shift_filenames[shift]
        path.write_bytes(cal.to_ical())
        output_files.append(path)

    return output_files

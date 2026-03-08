from __future__ import annotations

from duty_schedule.constants import (
    CAL_SHIFT_COLORS_CSS,
    SHIFT_PALETTE_CSS,
)
from duty_schedule.constants import (
    MONTHS_RU as _MONTHS_RU_1,
)
from duty_schedule.models import ShiftType

MONTHS_RU = _MONTHS_RU_1[1:]
_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_XLS_VERSION = "2"

_CITY_TO_RU = {"moscow": "Москва", "khabarovsk": "Хабаровск"}
_RU_TO_CITY = {"Москва": "moscow", "Хабаровск": "khabarovsk"}
_STYPE_TO_RU = {"flexible": "Гибкий", "5/2": "5/2"}
_RU_TO_STYPE = {"Гибкий": "flexible", "5/2": "5/2"}

_WEEKDAY_SHORT_TO_INT = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
_INT_TO_WEEKDAY_SHORT = {v: k.capitalize() for k, v in _WEEKDAY_SHORT_TO_INT.items()}
_WEEKDAY_INT_TO_RU = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
_WEEKDAY_RU_TO_INT = {v: k for k, v in _WEEKDAY_INT_TO_RU.items()}
_WEEKDAY_OPTIONS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_EMPTY_ROW: dict = {
    "Имя": "",
    "Город": "Москва",
    "График": "Гибкий",
    "Дежурный": True,
    "Всегда на деж.": False,
    "Только утро": False,
    "Только вечер": False,
    "Предпочт. смена": "",
    "Загрузка%": 100,
    "Макс. утренних": None,
    "Макс. вечерних": None,
    "Макс. ночных": None,
    "Макс. подряд": 6,
    "Подряд: утро": None,
    "Подряд: вечер": None,
    "Подряд: день": None,
    "Группа": "",
}

_DEFAULT_ROWS: list[dict] = [
    {**_EMPTY_ROW, "Имя": "Абашина", "Предпочт. смена": "Утро"},
    {**_EMPTY_ROW, "Имя": "Скрябин", "График": "5/2", "Только утро": True, "Всегда на деж.": True},
    {**_EMPTY_ROW, "Имя": "Ищенко"},
    {**_EMPTY_ROW, "Имя": "Корох"},
    {**_EMPTY_ROW, "Имя": "Ужахов"},
    {**_EMPTY_ROW, "Имя": "Вика", "Город": "Хабаровск"},
    {**_EMPTY_ROW, "Имя": "Голубев", "Город": "Хабаровск"},
    {**_EMPTY_ROW, "Имя": "Карпенко", "Город": "Хабаровск"},
]

_TABLE_KEY_PREFIX = "employees_table"

_SHIFTS_RU = ["Утро", "Вечер", "Ночь", "Рабочий день", "Выходной"]
_RU_TO_SHIFT = {
    "Утро": ShiftType.MORNING,
    "Вечер": ShiftType.EVENING,
    "Ночь": ShiftType.NIGHT,
    "Рабочий день": ShiftType.WORKDAY,
    "Выходной": ShiftType.DAY_OFF,
}
_SHIFT_TO_RU = {v: k for k, v in _RU_TO_SHIFT.items()}

_EMPTY_PIN_ROW: dict = {"Дата": None, "Сотрудник": "", "Смена": "Утро"}

_EmployeeDates = dict

_SHIFT_PALETTE = SHIFT_PALETTE_CSS

_CAL_SHIFT_COLORS = CAL_SHIFT_COLORS_CSS

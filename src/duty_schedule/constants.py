"""Schedule generator constants.

MAX_CONSECUTIVE_WORKING_DEFAULT (=6): применяется в greedy-планировании
(CLI, Streamlit, FastAPI и CP-SAT solver), когда у сотрудника не задан
явный Employee.max_consecutive_working.

MAX_CONSECUTIVE_WORKING_FLEX (=5): применяется только в postprocess
(scheduler/postprocess/*.py) для гибких дежурных (FLEXIBLE + on_duty,
не duty_only), у которых не задан явный Employee.max_consecutive_working —
позволяет ребалансировке сокращать длинные серии.
"""

from __future__ import annotations

MAX_CONSECUTIVE_WORKING_DEFAULT = 6
MAX_CONSECUTIVE_WORKING_FLEX = 5
MAX_CONSECUTIVE_OFF_DEFAULT = 100
MAX_BACKTRACK_DAYS = 3
MAX_BACKTRACK_ATTEMPTS = 10
MIN_WORK_BETWEEN_OFFS = 3

MONTHS_RU = [
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

SHIFT_COLORS_HEADER: dict[str, str] = {
    "morning": "FFC107",
    "evening": "3F51B5",
    "night": "673AB7",
    "workday": "009688",
    "day_off": "90A4AE",
    "vacation": "FF5722",
}

SHIFT_COLORS_CELL: dict[str, str] = {
    "morning": "FFE082",
    "evening": "C5CAE9",
    "night": "EDE7F6",
    "workday": "B2DFDB",
    "day_off": "ECEFF1",
    "vacation": "FFCCBC",
}

SHIFT_LABEL_CODES: dict[str, str] = {
    "morning": "У",
    "evening": "В",
    "night": "Н",
    "workday": "Р",
    "day_off": "–",
    "vacation": "О",
}

CODE_TO_SHIFT_KEY: dict[str, str] = {v: k for k, v in SHIFT_LABEL_CODES.items()}

SHIFT_PALETTE_CSS: dict[str, str] = {
    SHIFT_LABEL_CODES[k]: f"#{v}" for k, v in SHIFT_COLORS_HEADER.items()
}

CAL_SHIFT_COLORS_CSS: dict[str, str] = {
    SHIFT_LABEL_CODES[k]: f"#{v}" for k, v in SHIFT_COLORS_CELL.items()
}

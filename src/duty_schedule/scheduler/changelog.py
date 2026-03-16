from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ChangeEntry:
    stage: str
    action: str
    employee: str
    day: date
    detail: str = ""


@dataclass
class ChangeLog:
    entries: list[ChangeEntry] = field(default_factory=list)

    def add(
        self,
        stage: str,
        action: str,
        employee: str,
        day: date,
        detail: str = "",
    ) -> None:
        self.entries.append(
            ChangeEntry(stage=stage, action=action, employee=employee, day=day, detail=detail)
        )

    def filter_by_employee(self, name: str) -> list[ChangeEntry]:
        return [e for e in self.entries if e.employee == name]

    def filter_by_stage(self, stage: str) -> list[ChangeEntry]:
        return [e for e in self.entries if e.stage == stage]

from __future__ import annotations

from datetime import date

from duty_schedule.scheduler.changelog import ChangeEntry, ChangeLog


def test_changelog_add_and_filter() -> None:
    cl = ChangeLog()
    cl.add("balance_weekend", "swap", "Alice", date(2026, 3, 7), "morning → day_off")
    cl.add("target_adjust", "add_workday", "Bob", date(2026, 3, 10), "day_off → workday")
    cl.add("balance_weekend", "swap", "Alice", date(2026, 3, 14), "evening → day_off")

    assert len(cl.entries) == 3

    alice_entries = cl.filter_by_employee("Alice")
    assert len(alice_entries) == 2
    assert all(e.employee == "Alice" for e in alice_entries)

    bob_entries = cl.filter_by_employee("Bob")
    assert len(bob_entries) == 1
    assert bob_entries[0].action == "add_workday"

    weekend_entries = cl.filter_by_stage("balance_weekend")
    assert len(weekend_entries) == 2

    target_entries = cl.filter_by_stage("target_adjust")
    assert len(target_entries) == 1


def test_changelog_empty() -> None:
    cl = ChangeLog()
    assert cl.entries == []
    assert cl.filter_by_employee("Nobody") == []
    assert cl.filter_by_stage("nonexistent") == []


def test_change_entry_fields() -> None:
    entry = ChangeEntry(
        stage="balance_duty",
        action="swap",
        employee="Charlie",
        day=date(2026, 4, 1),
        detail="morning → workday",
    )
    assert entry.stage == "balance_duty"
    assert entry.action == "swap"
    assert entry.employee == "Charlie"
    assert entry.day == date(2026, 4, 1)
    assert entry.detail == "morning → workday"

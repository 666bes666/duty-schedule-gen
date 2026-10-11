"""CLI-интерфейс генератора графика дежурств."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from duty_schedule import __version__
from duty_schedule._errors_fmt import format_validation_errors
from duty_schedule.calendar import CalendarError, fetch_production_calendar
from duty_schedule.export.ics import export_ics
from duty_schedule.export.xls import export_xls
from duty_schedule.logging import get_logger, setup_logging
from duty_schedule.models import City, Config, Schedule, collect_config_issues
from duty_schedule.project import (
    ExportBlockedError,
    add_revision,
    current_schedule,
    ensure_exportable,
    load_project,
    new_project,
    serialize_project,
)
from duty_schedule.scheduler import ScheduleError, generate_schedule

app = typer.Typer(
    name="duty-schedule",
    help="Генератор графика дежурств с покрытием 24/7",
    add_completion=False,
)
console = Console()
logger = get_logger(__name__)


def _load_config(config_path: Path) -> Config:
    """Загрузить и провалидировать конфигурацию из YAML-файла."""
    if not config_path.exists():
        raise typer.BadParameter(f"Файл конфигурации не найден: {config_path}")
    try:
        with config_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return Config.model_validate(raw)
    except yaml.YAMLError as exc:
        raise typer.BadParameter(f"Ошибка разбора YAML: {exc}") from exc
    except ValidationError as exc:
        formatted = "\n".join(format_validation_errors(exc))
        raise typer.BadParameter(f"Ошибка валидации конфигурации:\n{formatted}") from exc


@app.command()
def generate(
    config_file: Annotated[Path, typer.Argument(help="Путь к YAML-файлу конфигурации")],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-o", help="Директория для результатов")
    ] = Path("output"),
    fmt: Annotated[str, typer.Option("--format", "-f", help="Формат: xls, ics, all")] = "all",
    holidays: Annotated[
        str | None, typer.Option("--holidays", help="Праздники YYYY-MM-DD через запятую")
    ] = None,
    seed: Annotated[
        int | None, typer.Option("--seed", "-s", help="Переопределить seed из конфигурации")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Подробный вывод")] = False,
    project_file: Annotated[
        Path | None, typer.Option("--project-file", help="Файл рабочего проекта")
    ] = None,
) -> None:
    """Сгенерировать график дежурств и экспортировать в XLS и/или ICS."""
    setup_logging("DEBUG" if verbose else "INFO")

    console.print(f"[bold cyan]Duty Schedule Generator v{__version__}[/bold cyan]")

    with console.status("Загрузка конфигурации..."):
        config = _load_config(config_file)

    if seed is not None:
        config = config.model_copy(update={"seed": seed})

    console.print(
        f"✓ Конфигурация загружена: [bold]{config.month:02d}.{config.year}[/bold], "
        f"{len(config.employees)} сотрудников"
    )

    errors, warnings = collect_config_issues(config)
    if errors:
        console.print("[bold red]✗ Ошибки конфигурации:[/bold red]")
        for msg in errors:
            console.print(f"  • {msg}")
        if warnings:
            console.print("[yellow]Предупреждения:[/yellow]")
            for msg in warnings:
                console.print(f"  • {msg}")
        raise typer.Exit(1)
    if warnings:
        console.print("[yellow]Предупреждения конфигурации:[/yellow]")
        for msg in warnings:
            console.print(f"  • {msg}")

    with console.status("Загрузка производственного календаря..."):
        holiday_set, short_days = _load_holidays(config, holidays)

    console.print(f"✓ Праздников в месяце: [bold]{len(holiday_set)}[/bold]")

    with console.status("Генерация расписания..."):
        try:
            schedule = generate_schedule(config, holiday_set)
        except ScheduleError as exc:
            console.print(f"[bold red]✗ Ошибка генерации:[/bold red] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"✓ Расписание сгенерировано: [bold]{len(schedule.days)} дней[/bold]")

    output_dir.mkdir(parents=True, exist_ok=True)
    project = add_revision(new_project(config), schedule)
    saved_path = project_file or output_dir / f"project_{config.year}_{config.month:02d}.duty.json"
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_bytes(serialize_project(project))
    console.print(f"✓ Рабочий проект: {saved_path}")
    if schedule.status != "ready":
        _print_diagnostics(schedule)
        raise typer.Exit(1)

    exported: list[str] = []
    fmt_lower = fmt.lower()

    if fmt_lower in ("xls", "all"):
        with console.status("Экспорт в XLS..."):
            xls_path = export_xls(schedule, output_dir, short_days=short_days)
        console.print(f"✓ XLS: [green]{xls_path}[/green]")
        exported.append(str(xls_path))

    if fmt_lower in ("ics", "all"):
        with console.status("Экспорт в ICS..."):
            ics_paths = export_ics(schedule, output_dir)
        for p in ics_paths:
            console.print(f"✓ ICS: [green]{p}[/green]")
        exported.extend(str(p) for p in ics_paths)

    if not exported:
        console.print(
            f"[yellow]Предупреждение: неизвестный формат '{fmt}'. "
            "Используйте: xls, ics, all[/yellow]"
        )

    _print_summary(schedule)


@app.command(name="generate-range")
def generate_range(
    config_file: Annotated[Path, typer.Argument(help="Путь к YAML-файлу конфигурации")],
    start: Annotated[str, typer.Option("--start", help="Начало диапазона MM.YYYY")],
    end: Annotated[str, typer.Option("--end", help="Конец диапазона MM.YYYY")],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-o", help="Директория для результатов")
    ] = Path("output"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Подробный вывод")] = False,
) -> None:
    setup_logging("DEBUG" if verbose else "INFO")
    console.print(f"[bold cyan]Duty Schedule Generator v{__version__}[/bold cyan]")

    config = _load_config(config_file)

    try:
        sm, sy = int(start.split(".")[0]), int(start.split(".")[1])
        em, ey = int(end.split(".")[0]), int(end.split(".")[1])
    except (ValueError, IndexError) as exc:
        raise typer.BadParameter(f"Формат даты: MM.YYYY (получено: {start}, {end})") from exc

    from duty_schedule.scheduler.multimonth import generate_multimonth

    with console.status(f"Генерация расписаний {start} — {end}..."):
        try:
            schedules = generate_multimonth(config, sm, sy, em, ey)
        except ScheduleError as exc:
            console.print(f"[bold red]✗ ScheduleError:[/bold red] {exc}")
            raise typer.Exit(1) from exc
        except CalendarError as exc:
            console.print(f"[bold red]✗ CalendarError:[/bold red] {exc}")
            raise typer.Exit(4) from exc
        except ValidationError as exc:
            console.print(f"[bold red]✗ ValidationError:[/bold red]\n{exc}")
            raise typer.Exit(3) from exc
        except ValueError as exc:
            console.print(f"[bold red]✗ ValueError:[/bold red] {exc}")
            raise typer.Exit(5) from exc

    for sched in schedules:
        m, y = sched.config.month, sched.config.year
        if sched.status != "ready":
            _print_diagnostics(sched)
            break
        xls_path = export_xls(sched, output_dir)
        console.print(f"✓ {m:02d}.{y}: [green]{xls_path}[/green] ({len(sched.days)} дней)")

    project = new_project(config)
    for schedule in schedules:
        project = add_revision(project, schedule)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "range.duty.json").write_bytes(serialize_project(project))
    completed = sum(s.status == "ready" for s in schedules)
    console.print(f"[bold green]Проверено: {completed} месяцев[/bold green]")
    if any(s.status != "ready" for s in schedules):
        raise typer.Exit(1)


@app.command()
def validate(
    config_file: Annotated[Path, typer.Argument(help="Путь к YAML-файлу конфигурации")],
) -> None:
    """Проверить конфигурацию без генерации расписания."""
    try:
        config = _load_config(config_file)
        errors, warnings = collect_config_issues(config)

        if errors:
            console.print("[bold red]✗ Найдены ошибки конфигурации:[/bold red]")
            for msg in errors:
                console.print(f"  • {msg}")
            if warnings:
                console.print("[yellow]Предупреждения:[/yellow]")
                for msg in warnings:
                    console.print(f"  • {msg}")
            raise typer.Exit(1)

        console.print("[bold green]✓ Конфигурация корректна[/bold green]")
        console.print(f"  Месяц/год: {config.month:02d}.{config.year}")
        console.print(f"  Сотрудников: {len(config.employees)}")

        moscow_duty = sum(1 for e in config.employees if e.city == City.MOSCOW and e.on_duty)
        khb_duty = sum(1 for e in config.employees if e.city == City.KHABAROVSK and e.on_duty)
        console.print(f"  Дежурных Москва: {moscow_duty}, Хабаровск: {khb_duty}")
        if warnings:
            console.print("[yellow]Есть предупреждения:[/yellow]")
            for msg in warnings:
                console.print(f"  • {msg}")
    except typer.BadParameter as exc:
        console.print(f"[bold red]✗ Ошибка:[/bold red] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def version() -> None:
    """Показать версию приложения."""
    console.print(f"duty-schedule v{__version__}")


def _load_holidays(config: Config, holidays_arg: str | None) -> tuple[set[date], set[date]]:
    from datetime import date as _date

    try:
        calendar = config.production_calendar or fetch_production_calendar(
            config.year, config.month
        )
        config.production_calendar = calendar
        return calendar.off_dates(), calendar.short_dates()
    except CalendarError as exc:
        logger.warning("production_calendar_api_unavailable", error=str(exc))
        console.print(f"[yellow]⚠ {exc}[/yellow]")

        if holidays_arg:
            console.print("[yellow]Используются праздники из --holidays[/yellow]")
            try:
                from duty_schedule.calendar import parse_manual_holidays

                return parse_manual_holidays(holidays_arg, config.year, config.month)
            except CalendarError as parse_exc:
                console.print(f"[bold red]✗ Ошибка разбора праздников:[/bold red] {parse_exc}")
                raise typer.Exit(1) from parse_exc

        import calendar as _calendar

        _, days = _calendar.monthrange(config.year, config.month)
        weekends = {
            _date(config.year, config.month, d)
            for d in range(1, days + 1)
            if _date(config.year, config.month, d).weekday() >= 5
        }
        console.print(
            "[yellow]Нет сохранённого производственного календаря нужного периода. "
            "Приближение используется только для диагностического черновика.[/yellow]"
        )
        from duty_schedule.calendar import compute_short_days

        return weekends, compute_short_days(config.year, config.month, weekends)


def _print_summary(schedule: Schedule) -> None:
    """Вывести итоговую статистику."""
    table = Table(title="Итог генерации", show_header=True, header_style="bold cyan")
    table.add_column("Показатель", style="dim")
    table.add_column("Значение", justify="right")

    meta = schedule.metadata
    table.add_row("Всего дней", str(len(schedule.days)))
    table.add_row("Ночных смен (чел.·дней)", str(meta.get("total_nights", "—")))
    table.add_row("Утренних смен", str(meta.get("total_mornings", "—")))
    table.add_row("Вечерних смен", str(meta.get("total_evenings", "—")))
    table.add_row("Праздников", str(meta.get("holidays_count", "—")))

    console.print(table)

    from duty_schedule.stats import build_assignments, compute_stats

    hours = Table(title="Нормы рабочих часов")
    for name in ("Сотрудник", "Календарная", "Скорректированная", "Выбранная", "Фактическая"):
        hours.add_column(name)
    for stat in compute_stats(
        schedule, build_assignments(schedule), meta.get("production_working_days", 0)
    ):
        hours.add_row(
            stat.name,
            str(stat.calendar_hours),
            str(stat.adjusted_hours),
            str(stat.selected_hours),
            str(stat.total_hours),
        )
    console.print(hours)


def _print_diagnostics(schedule: Schedule) -> None:
    console.print(
        "[bold yellow]Диагностический черновик; обычный экспорт заблокирован[/bold yellow]"
    )
    for problem in schedule.diagnostics:
        console.print(
            f"• {problem.date or ''} {problem.employee_name or ''}: {problem.detail}", markup=False
        )


@app.command(name="export-project")
def export_project(
    project_file: Annotated[Path, typer.Argument(help="Сохранённый файл проекта")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")] = Path("output"),
    period: Annotated[str | None, typer.Option("--period", help="Месяц YYYY-MM")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f")] = "all",
) -> None:
    try:
        project = load_project(project_file.read_bytes())
        if period is not None:
            project.selected_period = period
        schedule = current_schedule(project)
        if schedule is None:
            raise ValueError("Нет графика выбранного периода")
        schedule = ensure_exportable(schedule)
        if fmt not in ("xls", "ics", "all", "pdf"):
            raise ValueError("Формат: xls, ics, pdf, all")
        if fmt in ("xls", "all"):
            console.print(str(export_xls(schedule, output_dir)))
        if fmt in ("ics", "all"):
            for path in export_ics(schedule, output_dir):
                console.print(str(path))
        if fmt == "pdf":
            from duty_schedule.export.pdf import generate_schedule_pdf

            output_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = (
                output_dir / f"schedule_{schedule.config.year}_{schedule.config.month:02d}.pdf"
            )
            pdf_path.write_bytes(generate_schedule_pdf(schedule))
            console.print(str(pdf_path))
    except ExportBlockedError as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(1) from exc
    except (OSError, ValueError) as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    app()

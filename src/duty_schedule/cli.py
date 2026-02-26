"""CLI-интерфейс генератора графика дежурств."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from duty_schedule import __version__
from duty_schedule.calendar import CalendarError, fetch_holidays
from duty_schedule.export.ics import export_ics
from duty_schedule.export.xls import export_xls
from duty_schedule.logging import get_logger, setup_logging
from duty_schedule.models import City, Config, collect_config_issues
from duty_schedule.scheduler import ScheduleError, generate_schedule

app = typer.Typer(
    name="duty-schedule",
    help="Генератор графика дежурств с покрытием 24/7",
    add_completion=False,
)
console = Console()
logger = get_logger()


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
        raise typer.BadParameter(f"Ошибка валидации конфигурации:\n{exc}") from exc


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
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Подробный вывод")] = False,
) -> None:
    """Сгенерировать график дежурств и экспортировать в XLS и/или ICS."""
    setup_logging("DEBUG" if verbose else "INFO")

    console.print(f"[bold cyan]Duty Schedule Generator v{__version__}[/bold cyan]")

    with console.status("Загрузка конфигурации..."):
        config = _load_config(config_file)

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
        holiday_set = _load_holidays(config, holidays)

    console.print(f"✓ Праздников в месяце: [bold]{len(holiday_set)}[/bold]")

    with console.status("Генерация расписания..."):
        try:
            schedule = generate_schedule(config, holiday_set)
        except ScheduleError as exc:
            console.print(f"[bold red]✗ Ошибка генерации:[/bold red] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"✓ Расписание сгенерировано: [bold]{len(schedule.days)} дней[/bold]")

    exported: list[str] = []
    fmt_lower = fmt.lower()

    if fmt_lower in ("xls", "all"):
        with console.status("Экспорт в XLS..."):
            xls_path = export_xls(schedule, output_dir)
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


def _load_holidays(config: Config, holidays_arg: str | None) -> set:
    """Загрузить праздники из API или из аргумента командной строки."""
    from datetime import date as _date

    try:
        return fetch_holidays(config.year, config.month)
    except CalendarError as exc:
        logger.warning("API производственного календаря недоступен", error=str(exc))
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
            f"[yellow]Используются только выходные дни ({len(weekends)} дней). "
            "Укажите --holidays для точного производственного календаря.[/yellow]"
        )
        return weekends


def _print_summary(schedule) -> None:
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


if __name__ == "__main__":
    app()

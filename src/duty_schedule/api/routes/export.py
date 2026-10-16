from __future__ import annotations

import asyncio
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from duty_schedule.api.planning import plan_schedule
from duty_schedule.api.schemas import ErrorResponse, ScheduleNotReadyResponse
from duty_schedule.export.filenames import safe_filenames
from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.export.xls import export_xls
from duty_schedule.logging import get_logger, log_duration
from duty_schedule.models import Config, Schedule
from duty_schedule.project import ensure_exportable
from duty_schedule.scheduler import generate_schedule
from duty_schedule.scheduler.core import ScheduleError

logger = get_logger(__name__)
router = APIRouter(prefix="/export", tags=["export"])

XLS_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"


def _binary_responses(*media_types: str) -> dict[int | str, dict[str, Any]]:
    responses: dict[int | str, dict[str, Any]] = {
        code: {"model": ErrorResponse} for code in (400, 401, 403, 429, 500, 502)
    }
    responses[409] = {
        "model": ScheduleNotReadyResponse,
        "description": "Schedule failed mandatory checks",
    }
    responses[200] = {
        "content": {
            media_type: {"schema": {"type": "string", "format": "binary"}}
            for media_type in media_types
        },
        "headers": {
            "Content-Disposition": {
                "schema": {"type": "string"},
                "description": "RFC 5987 attachment filename",
            }
        },
    }
    return responses


def _content_disposition(filename: str) -> str:
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def _check_employee(config: Config, employee_name: str | None) -> None:
    if employee_name is not None and employee_name not in {
        employee.name for employee in config.employees
    }:
        raise ScheduleError(f"Сотрудник «{employee_name}» не найден")


def _xls_response(schedule: Schedule) -> StreamingResponse:
    schedule = ensure_exportable(schedule)
    with log_duration(logger, "export_done", format="xls"), tempfile.TemporaryDirectory() as tmpdir:
        xls_bytes = export_xls(schedule, Path(tmpdir)).read_bytes()
    filename = f"schedule_{schedule.config.year}_{schedule.config.month:02d}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type=XLS_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def _pdf_response(schedule: Schedule, page_size: str) -> Response:
    from duty_schedule.export.pdf import generate_schedule_pdf

    schedule = ensure_exportable(schedule)
    with log_duration(logger, "export_done", format="pdf"):
        pdf_bytes = generate_schedule_pdf(schedule, page_size)
    filename = f"schedule_{schedule.config.year}_{schedule.config.month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type=PDF_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


def _ics_response(schedule: Schedule, employee_name: str | None) -> Response:
    _check_employee(schedule.config, employee_name)
    schedule = ensure_exportable(schedule)
    with log_duration(logger, "export_done", format="ics"):
        if employee_name is not None:
            content = generate_employee_ics_bytes(schedule, employee_name)
            filename = safe_filenames([f"schedule_{employee_name}"], ".ics")[0]
            return Response(
                content=content,
                media_type="text/calendar",
                headers={"Content-Disposition": _content_disposition(filename)},
            )
        names = [employee.name for employee in schedule.config.employees]
        filenames = safe_filenames(names, ".ics")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, filename in zip(names, filenames, strict=True):
                archive.writestr(filename, generate_employee_ics_bytes(schedule, name))
    filename = f"schedules_{schedule.config.year}_{schedule.config.month:02d}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/xls", response_class=Response, responses=_binary_responses(XLS_MEDIA_TYPE))
async def export_xls_endpoint(config: Config) -> Response:
    schedule = await asyncio.to_thread(plan_schedule, config, generate_schedule)
    return await asyncio.to_thread(_xls_response, schedule)


@router.post("/pdf", response_class=Response, responses=_binary_responses(PDF_MEDIA_TYPE))
async def export_pdf_endpoint(
    config: Config, page_size: str = Query(default="A3", pattern="^(A3|A4)$")
) -> Response:
    schedule = await asyncio.to_thread(plan_schedule, config, generate_schedule)
    return await asyncio.to_thread(_pdf_response, schedule, page_size)


@router.post(
    "/ics", response_class=Response, responses=_binary_responses("text/calendar", "application/zip")
)
async def export_ics_endpoint(
    config: Config, employee_name: str | None = Query(default=None)
) -> Response:
    _check_employee(config, employee_name)
    schedule = await asyncio.to_thread(plan_schedule, config, generate_schedule)
    return await asyncio.to_thread(_ics_response, schedule, employee_name)


@router.post("/revision/xls", response_class=Response, responses=_binary_responses(XLS_MEDIA_TYPE))
async def export_revision_xls(schedule: Schedule) -> Response:
    return await asyncio.to_thread(_xls_response, schedule)


@router.post("/revision/pdf", response_class=Response, responses=_binary_responses(PDF_MEDIA_TYPE))
async def export_revision_pdf(
    schedule: Schedule, page_size: str = Query(default="A3", pattern="^(A3|A4)$")
) -> Response:
    return await asyncio.to_thread(_pdf_response, schedule, page_size)


@router.post(
    "/revision/ics",
    response_class=Response,
    responses=_binary_responses("text/calendar", "application/zip"),
)
async def export_revision_ics(
    schedule: Schedule, employee_name: str | None = Query(default=None)
) -> Response:
    return await asyncio.to_thread(_ics_response, schedule, employee_name)

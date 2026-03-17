from __future__ import annotations

import asyncio
import io
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse

from duty_schedule.calendar import fetch_holidays
from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.export.xls import export_xls
from duty_schedule.logging import get_logger
from duty_schedule.models import Config
from duty_schedule.scheduler import generate_schedule

logger = get_logger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

XLS_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"


def _content_disposition(filename: str) -> str:
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


@router.post("/xls")
async def export_xls_endpoint(config: Config) -> StreamingResponse:
    logger.info("export_start", format="xls")
    holidays, short_days = await asyncio.to_thread(fetch_holidays, config.year, config.month)
    schedule = await asyncio.to_thread(generate_schedule, config, holidays)

    def _build_xls() -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            xls_path = export_xls(schedule, Path(tmpdir), short_days=short_days)
            return xls_path.read_bytes()

    xls_bytes = await asyncio.to_thread(_build_xls)
    filename = f"schedule_{config.year}_{config.month:02d}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type=XLS_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/pdf")
async def export_pdf_endpoint(
    config: Config,
    page_size: str = Query(default="A3", pattern="^(A3|A4)$"),
) -> Response:
    logger.info("export_start", format="pdf")
    from duty_schedule.export.pdf import generate_schedule_pdf

    holidays, short_days = await asyncio.to_thread(fetch_holidays, config.year, config.month)
    schedule = await asyncio.to_thread(generate_schedule, config, holidays)
    pdf_bytes = await asyncio.to_thread(generate_schedule_pdf, schedule, page_size, short_days)
    filename = f"schedule_{config.year}_{config.month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type=PDF_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/ics")
async def export_ics_endpoint(
    config: Config,
    employee_name: str | None = Query(default=None),
) -> Response:
    logger.info("export_start", format="ics")
    holidays, _short_days = await asyncio.to_thread(fetch_holidays, config.year, config.month)
    schedule = await asyncio.to_thread(generate_schedule, config, holidays)

    if employee_name:
        known_names = {emp.name for emp in config.employees}
        if employee_name not in known_names:
            detail = f"Сотрудник \u00ab{employee_name}\u00bb не найден"
            body = f'{{"error":"schedule_error","detail":"{detail}"}}'
            return Response(
                content=body,
                status_code=400,
                media_type="application/json",
            )
        ics_bytes = await asyncio.to_thread(generate_employee_ics_bytes, schedule, employee_name)
        filename = f"schedule_{employee_name}.ics"
        return Response(
            content=ics_bytes,
            media_type="text/calendar",
            headers={"Content-Disposition": _content_disposition(filename)},
        )

    all_names = [emp.name for emp in config.employees]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in all_names:
            ics_bytes = generate_employee_ics_bytes(schedule, name)
            zf.writestr(f"{name}.ics", ics_bytes)
    buf.seek(0)
    filename = f"schedules_{config.year}_{config.month:02d}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )

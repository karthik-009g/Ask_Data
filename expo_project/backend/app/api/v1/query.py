from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import require_employee
from app.db.mongo import UserDoc
from app.schemas.query import ExportRequest, NLQueryRequest
from app.services.ai_query_service import run_nl_query
from app.services.export_service import export_csv, export_excel, export_pdf

router = APIRouter(tags=["query"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/query")
@limiter.limit("20/minute")
def query_data(request: Request, payload: NLQueryRequest, employee: UserDoc = Depends(require_employee)):
    _ = request
    try:
        return run_nl_query(employee, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/export")
@limiter.limit("10/minute")
def export_data(request: Request, payload: ExportRequest, employee: UserDoc = Depends(require_employee)):
    _ = request
    try:
        result = run_nl_query(employee, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    format_type = (payload.format or "csv").lower()
    rows = result["rows"]

    if format_type == "csv":
        content = export_csv(rows)
        return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=result.csv"})
    if format_type in {"excel", "xlsx"}:
        content = export_excel(rows)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=result.xlsx"})
    if format_type == "pdf":
        content = export_pdf(rows)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=result.pdf"})

    raise HTTPException(status_code=400, detail="Unsupported format")

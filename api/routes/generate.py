"""POST /api/generate — validated pitch data in, deliverable ZIP out.

The ZIP is assembled in memory from fixed entry names; nothing in the request
selects server-side paths. When SAVE_GENERATED_ZIPS is enabled a copy is
written under the configured OUTPUT_DIR for local debugging.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.schemas import GenerateRequest
from hackpack.generators.bundle import build_deliverable_zip

router = APIRouter(tags=["generate"])


@router.post("/generate")
def generate(request: GenerateRequest) -> Response:
    try:
        zip_bytes, filename = build_deliverable_zip(
            request.deck,
            evidence=request.evidence,
            demo_duration_seconds=request.demo_duration_seconds,
        )
    except Exception as exc:  # generation bug; surface a readable message only
        raise HTTPException(
            status_code=422,
            detail=f"Deliverable generation failed ({type(exc).__name__}); check the deck content and retry.",
        ) from exc

    try:
        from config import settings

        if settings.SAVE_GENERATED_ZIPS:
            out_dir = Path(settings.OUTPUT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / filename).write_bytes(zip_bytes)
    except OSError:
        pass  # saving a debug copy must never fail the request

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

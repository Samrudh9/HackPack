"""POST /api/pitch — generate verified six-slide pitch content (JSON only).

No files are created here; ``/api/generate`` turns the returned deck into the
deliverable ZIP. Blocking model calls run in the FastAPI threadpool.
"""
from fastapi import APIRouter, HTTPException

from api.schemas import PitchRequest, PitchResponse
from hackpack.engine.pitch_builder import build_pitch
from hackpack.engine.verifier import verify_claims
from hackpack.llm_client import LLMClient, LLMConfigurationError, LLMOutputError

router = APIRouter(tags=["pitch"])


@router.post("/pitch", response_model=PitchResponse)
def pitch(request: PitchRequest) -> PitchResponse:
    try:
        deck = build_pitch(request.evidence, request.brief, request.team, client=LLMClient())
    except (LLMConfigurationError, LLMOutputError) as exc:
        # Fallback is disabled in this deployment and the model failed.
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI model is unavailable and the deterministic fallback is disabled "
                f"({type(exc).__name__}). Configure a model or enable LLM_FALLBACK_ENABLED."
            ),
        ) from exc
    deck = verify_claims(deck, request.evidence, request.team)
    return PitchResponse(
        deck=deck,
        generation_mode=deck.generation_mode,
        warnings=deck.generation_warnings,
    )

# src/tma_api/spreads/router.py
from typing import Any, Dict

from fastapi import APIRouter, Depends, status, Response

from ..api_response import APIResponse, APIError
from ..auth.router import get_current_user
from .service import SpreadService
from .models import (
    SpreadQuestionCreate,
    SpreadQuestionModel,
    SpreadQuestionsList,
)
from . import models

router = APIRouter(prefix="/spreads", tags=["spreads"])
service = SpreadService()


def _error_response(
    response: Response,
    http_status: int,
    code: str,
    message: str,
    details: Dict[str, Any] | None = None,
) -> APIResponse:
    response.status_code = http_status
    return APIResponse(
        ok=False,
        error=APIError(
            code=code,
            message=message,
            details=details or {},
        ),
    )


# 1. GET /spreads — список
@router.get("", response_model=APIResponse)
def list_spreads(
    response: Response,
    page: int = 1,
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    if page < 1 or limit < 1:
        return _error_response(
            response,
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
            "page and limit must be >= 1",
            {"page": page, "limit": limit},
        )

    data = service.get_spreads_list(user_id=user["id"], page=page, limit=limit)
    return APIResponse(ok=True, data=data)


# 2. GET /spreads/{spread_id}
@router.get("/{spread_id}", response_model=APIResponse)
def get_spread(
    spread_id: int,
    response: Response,
    user: dict = Depends(get_current_user),
):
    spread = service.get_spread(user_id=user["id"], spread_id=spread_id)

    if spread is None:
        return _error_response(
            response,
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "Spread not found",
            {"spread_id": spread_id},
        )

    return APIResponse(ok=True, data=spread)


# 3. POST /spreads — авто и интерактив
@router.post("", response_model=APIResponse)
def create_spread(
    body: models.SpreadCreateIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]

    try:
        if body.mode == "auto":
            result = service.create_auto_spread(
                user_id=user_id,
                spread_type=body.spread_type,
                category=body.category,
                question=body.question,
            )
            return APIResponse(ok=True, data=result, error=None)

        elif body.mode == "interactive":
            result = service.create_interactive_session(
                user_id=user_id,
                spread_type=body.spread_type,
                category=body.category,
                positions=getattr(body, "positions", []),
                choices_per_position=getattr(body, "choices_per_position", 0),
            )
            return APIResponse(ok=True, data=result, error=None)

        else:
            return _error_response(
                response,
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                "Unknown mode for spread creation",
                {"mode": body.mode},
            )

    except Exception as e:
        return _error_response(
            response,
            status.HTTP_400_BAD_REQUEST,
            "bad_request",
            str(e),
        )


# 4. POST /spreads/session/{id}/select_card
@router.post("/session/{session_id}/select_card", response_model=APIResponse)
def select_card(
    session_id: str,
    body: models.SpreadSelectCardIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    session = service.select_card(session_id, body.position, body.choice_index)

    if not session:
        return _error_response(
            response,
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "Session not found",
            {"session_id": session_id},
        )

    if session.get("status") == "awaiting_selection":
        return APIResponse(ok=True, data=session)

    if "spread" in session:
        return APIResponse(ok=True, data=session["spread"])

    return _error_response(
        response,
        status.HTTP_400_BAD_REQUEST,
        "bad_request",
        "Invalid session state",
        {"session_id": session_id, "session": session},
    )


# 5. GET /spreads/{spread_id}/questions
@router.get("/{spread_id}/questions", response_model=APIResponse)
def get_spread_questions(
    spread_id: int,
    response: Response,
    user: dict = Depends(get_current_user),
):
    try:
        items = service.get_spread_questions(
            user_id=user["id"],
            spread_id=spread_id,
        )
        return APIResponse(ok=True, data=items, error=None)
    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return APIResponse(
            ok=False,
            data=None,
            error=APIError(code="not_found", message=str(e)),
        )


# 6. POST /spreads/{spread_id}/questions
@router.post("/{spread_id}/questions", response_model=APIResponse)
def add_spread_question(
    spread_id: int,
    body: models.SpreadQuestionCreate,
    response: Response,
    user: dict = Depends(get_current_user),
):
    try:
        item = service.add_spread_question(
            user_id=user["id"],
            spread_id=spread_id,
            question=body.question,
        )
        return APIResponse(ok=True, data=item, error=None)
    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return APIResponse(
            ok=False,
            data=None,
            error=APIError(code="not_found", message=str(e)),
        )

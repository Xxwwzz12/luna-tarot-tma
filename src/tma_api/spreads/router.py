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
        data=None,
        error=APIError(
            code=code,
            message=message,
            details=details or {},
        ),
    )


# 1. GET /spreads — список раскладов
@router.get("", response_model=APIResponse)
def list_spreads(
    response: Response,
    page: int = 1,
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    if page < 1 or limit < 1:
        return _error_response(
            response=response,
            http_status=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message="page and limit must be >= 1",
            details={"page": page, "limit": limit},
        )

    data = service.get_spreads_list(
        user_id=user["id"],
        page=page,
        limit=limit,
    )
    # ТЗ: заворачиваем в APIResponse(ok=True, data=data, error=None)
    return APIResponse(ok=True, data=data, error=None)


# 2. GET /spreads/{spread_id} — детальный расклад
@router.get("/{spread_id}", response_model=APIResponse)
def get_spread(
    spread_id: int,
    response: Response,
    user: dict = Depends(get_current_user),
):
    detail = service.get_spread(
        user_id=user["id"],
        spread_id=spread_id,
    )

    if detail is None:
        return _error_response(
            response=response,
            http_status=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Spread not found",
            details={"spread_id": spread_id},
        )

    return APIResponse(ok=True, data=detail, error=None)


# 3. POST /spreads — создать расклад (async, для AI)
@router.post("", response_model=APIResponse)
async def create_spread(
    body: models.SpreadCreateIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]

    try:
        if body.mode == "auto":
            # ТЗ: обязательный await, сервис сам содержит AI-логику / fallback
            detail = await service.create_auto_spread(
                user_id=user_id,
                spread_type=body.spread_type,
                category=body.category,
                question=body.question,
            )
            # ТЗ: возвращаем APIResponse(ok=True, data=SpreadDetail, error=None)
            return APIResponse(ok=True, data=detail, error=None)

        elif body.mode == "interactive":
            # На будущее: интерактивный режим тоже может вызывать AI внутри сервиса
            detail = await service.create_interactive_session(
                user_id=user_id,
                spread_type=body.spread_type,
                category=body.category,
                positions=getattr(body, "positions", []),
                choices_per_position=getattr(body, "choices_per_position", 0),
            )
            return APIResponse(ok=True, data=detail, error=None)

        else:
            return _error_response(
                response=response,
                http_status=status.HTTP_400_BAD_REQUEST,
                code="validation_error",
                message="Unknown mode for spread creation",
                details={"mode": body.mode},
            )

    except Exception as e:
        # Тут могут быть ошибки AI, валидации и т.п. — наружу отдаём 400
        return _error_response(
            response=response,
            http_status=status.HTTP_400_BAD_REQUEST,
            code="bad_request",
            message=str(e),
        )


# 4. POST /spreads/session/{session_id}/select_card — выбор карты в интерактивной сессии
@router.post("/session/{session_id}/select_card", response_model=APIResponse)
def select_card(
    session_id: str,
    body: models.SpreadSelectCardIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    session = service.select_card(
        session_id=session_id,
        position=body.position,
        choice_index=body.choice_index,
    )

    if not session:
        return _error_response(
            response=response,
            http_status=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Session not found",
            details={"session_id": session_id},
        )

    if session.get("status") == "awaiting_selection":
        return APIResponse(ok=True, data=session, error=None)

    if "spread" in session:
        return APIResponse(ok=True, data=session["spread"], error=None)

    return _error_response(
        response=response,
        http_status=status.HTTP_400_BAD_REQUEST,
        code="bad_request",
        message="Invalid session state",
        details={"session_id": session_id, "session": session},
    )


# 5. GET /spreads/{spread_id}/questions — список вопросов (синхронный)
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
            error=APIError(
                code="not_found",
                message=str(e),
            ),
        )


# 6. POST /spreads/{spread_id}/questions — задать вопрос (async, AI-ответ)
@router.post("/{spread_id}/questions", response_model=APIResponse)
async def add_spread_question(
    spread_id: int,
    body: SpreadQuestionCreate,
    response: Response,
    user: dict = Depends(get_current_user),
):
    try:
        question_text = body.question

        # ТЗ: async endpoint, ждём AI/интерпретацию внутри сервиса
        item = await service.add_spread_question(
            user_id=user["id"],
            spread_id=spread_id,
            question=question_text,
        )
        # ТЗ: APIResponse(ok=True, data=item, error=None)
        return APIResponse(ok=True, data=item, error=None)

    except ValueError as e:
        response.status_code = status.HTTP_404_NOT_FOUND
        return APIResponse(
            ok=False,
            data=None,
            error=APIError(
                code="not_found",
                message=str(e),
            ),
        )

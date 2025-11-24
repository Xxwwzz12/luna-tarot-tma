# src/tma_api/app.py
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi.middleware.cors import CORSMiddleware

from .api_response import APIResponse, APIError

# ---- Корректные импорты роутеров по ТЗ №7 ----
from .auth.router import router as auth_router          # src/tma_api/auth/router.py
from .routers import profile                            # src/tma_api/routers/profile.py
from .spreads.router import router as spreads_router    # src/tma_api/spreads/router.py

logger = logging.getLogger(__name__)


# ----------------------------------------------------
# FastAPI приложение
# ----------------------------------------------------
app = FastAPI(
    title="Luna Tarot TMA API",
    version="0.1.0",
    description="HTTP API для Telegram Mini App версии Таро-бота Луна",
)


# ----------------------------------------------------
# CORS middleware (по ТЗ)
# ----------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # на время разработки
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------
# Health-check
# ----------------------------------------------------
@app.get("/health", response_model=APIResponse)
async def health_check() -> APIResponse:
    return APIResponse(ok=True, data={"status": "ok"})


# ----------------------------------------------------
# Глобальные обработчики ошибок
# ----------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception in TMA API", exc_info=exc)

    return JSONResponse(
        status_code=500,
        content=APIResponse(
            ok=False,
            error=APIError(code="internal_error", message="Internal server error"),
        ).model_dump(),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):

    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content=APIResponse(
                ok=False,
                error=APIError(
                    code="not_found",
                    message="Resource not found",
                    details={"path": request.url.path},
                ),
            ).model_dump(),
        )

    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            ok=False,
            error=APIError(
                code="http_error",
                message=str(exc.detail),
                details={"status_code": exc.status_code},
            ),
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):

    logger.warning("Validation error in TMA API", exc_info=exc)

    return JSONResponse(
        status_code=422,
        content=APIResponse(
            ok=False,
            error=APIError(
                code="validation_error",
                message="Request validation error",
                details={"errors": exc.errors()},
            ),
        ).model_dump(),
    )


# ----------------------------------------------------
# Подключение роутеров (без prefix — prefix указан внутри router)
# ----------------------------------------------------
app.include_router(auth_router)
app.include_router(profile.router)
app.include_router(spreads_router)


# ----------------------------------------------------
# Локальный запуск
# ----------------------------------------------------
# uvicorn src.tma_api.app:app --reload

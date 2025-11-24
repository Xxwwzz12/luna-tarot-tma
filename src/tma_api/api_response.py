from typing import Any, Optional
from pydantic import BaseModel


class APIError(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class APIResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[APIError] = None

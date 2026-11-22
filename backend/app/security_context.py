# backend/app/security_context.py
from contextvars import ContextVar
from dataclasses import dataclass

@dataclass(frozen=True)
class RequestPrincipal:
    role: str  # HOD | FACULTY | ADMIN_CLERK | STUDENT
    user_email: str

_principal_ctx: ContextVar[RequestPrincipal] = ContextVar("principal_ctx")

def set_principal(role: str, user_email: str):
    return _principal_ctx.set(RequestPrincipal(role=role, user_email=user_email))

def get_principal() -> RequestPrincipal:
    try:
        return _principal_ctx.get()
    except LookupError:
        return RequestPrincipal(role="STUDENT", user_email="")


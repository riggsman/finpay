from contextvars import ContextVar

# Per-request metadata (IP, user agent, request id) made available to services
# for audit logging without threading it through every function signature.
# anyio propagates contextvars into the threadpool that runs sync endpoints.
_request_context: ContextVar[dict] = ContextVar("request_context", default={})


def set_request_context(**kwargs) -> None:
    _request_context.set(kwargs)


def get_request_context() -> dict:
    return _request_context.get() or {}

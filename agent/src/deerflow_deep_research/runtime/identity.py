"""Trusted identity resolution for Deep Research runtime authority.

@impl RUI-002

Deep Research requires an explicit, server-injected ``runtime.context["user_id"]``.
DeerFlow's generic ``resolve_runtime_user_id`` deliberately falls back to the
synthetic ``default`` user when runtime/auth context is missing; that fallback is
useful to generic tools but too permissive for this authority boundary, so it is
never consulted here.
"""

from __future__ import annotations

from typing import Any


class TrustedIdentityError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def require_trusted_user_id(runtime: Any) -> str:
    """Return the explicit server-injected user id or fail closed.

    Unlike ``resolve_runtime_user_id``, this never returns ``default`` for a
    missing/empty identity: the Gateway overwrites both body context and body
    config context with the authenticated (or explicit auth-disabled ``default``)
    id, so an absent value means the trusted injection path did not run.
    """
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        raise TrustedIdentityError("identity_missing", "runtime context is unavailable")
    raw = context.get("user_id")
    if not isinstance(raw, str) or not raw.strip():
        raise TrustedIdentityError("identity_missing", "explicit runtime user_id is required")
    return raw


def require_context_value(runtime: Any, key: str, code: str) -> Any:
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        value = context.get(key)
        if value not in (None, ""):
            return value
    config = getattr(runtime, "config", None)
    if isinstance(config, dict):
        configurable = config.get("configurable")
        if isinstance(configurable, dict):
            value = configurable.get(key)
            if value not in (None, ""):
                return value
    raise TrustedIdentityError(code, f"trusted runtime {key} is required")


__all__ = ["TrustedIdentityError", "require_context_value", "require_trusted_user_id"]

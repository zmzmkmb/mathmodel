"""Deterministic gates for accepting coder output into the writing stage."""

from __future__ import annotations

from app.schemas.A2A import CoderToWriter


def validate_coder_response(response: CoderToWriter) -> tuple[bool, str]:
    """Require executed code and a non-empty report before writing."""
    if not response.success:
        return False, response.error_message or "coder reported failure"
    if not response.executed_code:
        return False, "coder did not execute code"
    if not (response.code_response or "").strip():
        return False, "coder returned an empty validation report"
    return True, response.validation_summary or "code executed and report returned"

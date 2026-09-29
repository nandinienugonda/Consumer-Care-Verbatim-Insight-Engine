"""Liveness and readiness reports."""

from pydantic import BaseModel


class CheckResult(BaseModel):
    ok: bool
    detail: str | None = None


class ReadinessReport(BaseModel):
    ready: bool
    checks: dict[str, CheckResult]

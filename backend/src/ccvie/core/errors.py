"""Typed errors. The API layer maps each to an HTTP status and a stable error code."""


class CCVIEError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Unauthenticated(CCVIEError):
    status_code = 401
    code = "unauthenticated"


class Forbidden(CCVIEError):
    status_code = 403
    code = "forbidden"


class NotFound(CCVIEError):
    status_code = 404
    code = "not_found"


class DependencyUnavailable(CCVIEError):
    status_code = 503
    code = "dependency_unavailable"


class AccessViolation(CCVIEError):
    """A retriever returned data outside the AccessFilter. Always a bug; fail closed."""

    status_code = 500
    code = "access_violation"

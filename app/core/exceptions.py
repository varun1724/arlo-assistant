"""Application exception hierarchy."""


class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, code: str = "error", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="not_found", status_code=404)


class AuthError(AppError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="auth_error", status_code=401)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict"):
        super().__init__(message, code="conflict", status_code=409)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, code="validation_error", status_code=422)

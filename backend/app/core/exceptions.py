from __future__ import annotations


class AppError(Exception):
    def __init__(self, status_code: int, detail: str, error_type: str = "about:blank"):
        self.status_code = status_code
        self.detail = detail
        self.error_type = error_type


class NotFoundError(AppError):
    def __init__(self, detail: str = "Nicht gefunden"):
        super().__init__(404, detail, "about:blank")


class ForbiddenError(AppError):
    def __init__(self, detail: str = "Nicht erlaubt"):
        super().__init__(403, detail, "about:blank")


class UnauthorizedError(AppError):
    def __init__(self, detail: str = "Nicht authentifiziert"):
        super().__init__(401, detail, "about:blank")


class ConflictError(AppError):
    def __init__(self, detail: str = "Konflikt"):
        super().__init__(409, detail, "about:blank")


class ValidationError(AppError):
    def __init__(self, detail: str = "Ungültige Eingabe"):
        super().__init__(422, detail, "https://tasks.example.com/errors/validation")

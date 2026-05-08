"""
Domain exception hierarchy.

All application errors subclass AppError which carries an HTTP status code,
an error code (machine-readable slug), and a human message.

FastAPI exception handlers in app/main.py map these to structured JSON responses.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class AppError(Exception):
    """Base class for all application exceptions."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: Any = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        self.context = context or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(error_code={self.error_code!r}, message={self.message!r})"


# Auth Errors

class AuthError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "auth_error"
    message = "Authentication failed"


class TokenInvalidError(AuthError):
    error_code = "token_invalid"
    message = "Token is invalid or malformed"


class TokenExpiredError(AuthError):
    error_code = "token_expired"
    message = "Token has expired"


class CredentialsInvalidError(AuthError):
    error_code = "credentials_invalid"
    message = "Invalid username or password"


class AccountInactiveError(AuthError):
    error_code = "account_inactive"
    message = "This account is deactivated"


# Permission Errors

class PermissionError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    error_code = "permission_denied"
    message = "You do not have permission to perform this action"


class RoleRequiredError(PermissionError):
    error_code = "role_required"

    def __init__(self, required_roles: list[str]) -> None:
        super().__init__(
            message=f"One of the following roles is required: {', '.join(required_roles)}",
            context={"required_roles": required_roles},
        )


# Not Found Errors

class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"
    message = "Resource not found"

    def __init__(self, resource: str, identifier: Any = None) -> None:
        msg = f"{resource} not found"
        if identifier is not None:
            msg = f"{resource} '{identifier}' not found"
        super().__init__(message=msg, context={"resource": resource, "id": str(identifier) if identifier else None})


# Validation / Business Rule Errors

class ValidationError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    message = "Validation failed"


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    error_code = "conflict"
    message = "Resource already exists or conflicts with current state"


class BusinessRuleError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "business_rule_violation"
    message = "Operation violates a business rule"


# Inventory Errors

class InsufficientInventoryError(BusinessRuleError):
    error_code = "insufficient_inventory"

    def __init__(self, product: str, requested: Any, available: Any) -> None:
        super().__init__(
            message=f"Insufficient inventory for '{product}': requested {requested}, available {available}",
            context={"product": product, "requested": str(requested), "available": str(available)},
        )


class InventoryMovementError(BusinessRuleError):
    error_code = "inventory_movement_error"


# Financial Errors

class InsufficientFundsError(BusinessRuleError):
    error_code = "insufficient_funds"
    message = "Insufficient funds for this transaction"


class LedgerBalanceError(BusinessRuleError):
    error_code = "ledger_balance_error"
    message = "Ledger balance inconsistency detected"


class PaymentAmountError(BusinessRuleError):
    error_code = "payment_amount_error"
    message = "Payment amount does not match the voucher total"


# Voucher Errors

class VoucherLockedError(BusinessRuleError):
    error_code = "voucher_locked"
    message = "This voucher is locked and cannot be modified"


class VoucherAlreadyCancelledError(BusinessRuleError):
    error_code = "voucher_already_cancelled"
    message = "This voucher has already been cancelled"


# Infrastructure Errors

class DatabaseError(AppError):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "database_error"
    message = "A database error occurred"


class CacheError(AppError):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "cache_error"
    message = "A cache operation failed"


class ExternalServiceError(AppError):
    status_code = HTTPStatus.BAD_GATEWAY
    error_code = "external_service_error"
    message = "An external service is unavailable"


# Rate Limiting

class RateLimitError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"
    message = "Too many requests — please slow down"


# Concurrency Errors

class OptimisticLockError(AppError):
    status_code = HTTPStatus.CONFLICT
    error_code = "optimistic_lock_conflict"
    message = "The record was modified by another request — please reload and retry"

    def __init__(self, resource: str, expected: int, actual: int) -> None:
        super().__init__(
            message=(
                f"{resource} version conflict: expected {expected}, "
                f"got {actual}. Reload and retry."
            ),
            context={"resource": resource, "expected": expected, "actual": actual},
        )


class IdempotencyConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    error_code = "idempotency_conflict"
    message = (
        "An idempotency key was reused with a different request body. "
        "Use a new key for a different operation."
    )


class DeadlockError(AppError):
    status_code = HTTPStatus.CONFLICT
    error_code = "deadlock_detected"
    message = "A database deadlock was detected — please retry the operation"


# Reconciliation / Integrity Errors

class IntegrityCheckError(AppError):
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "integrity_check_failed"
    message = "A data integrity check detected an inconsistency"

    def __init__(self, details: list[str]) -> None:
        super().__init__(
            message=f"Integrity check failed: {len(details)} issue(s) detected",
            context={"issues": details},
        )

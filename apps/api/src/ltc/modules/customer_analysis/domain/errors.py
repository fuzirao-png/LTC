"""Customer Analysis domain errors."""

from __future__ import annotations


class CustomerAnalysisError(RuntimeError):
    """Base error for the Customer Analysis bounded context."""


class ResourceNotFoundError(CustomerAnalysisError):
    pass


class VersionConflictError(CustomerAnalysisError):
    pass


class InvalidStateError(CustomerAnalysisError):
    pass


class InvalidDimensionError(CustomerAnalysisError):
    pass


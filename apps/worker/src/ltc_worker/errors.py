class WorkerError(Exception):
    """Base worker error."""


class LeaseLost(WorkerError):
    """Raised when a claimed job lease is no longer valid."""


class RetryableError(WorkerError):
    """Raised when a job should be retried through the jobs use case."""


class PayloadValidationError(WorkerError):
    """Raised when the job payload does not match the handler contract."""


class UnsupportedJobTypeError(WorkerError):
    """Raised when no handler is registered for a job type."""

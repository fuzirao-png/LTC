class CustomerOperationError(Exception):
    """Base error for customer operation use cases."""


class CustomerOperationNotFound(CustomerOperationError):
    """Raised when a customer operation resource cannot be found."""






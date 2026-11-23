from ltc.modules.customer_operation.application.service import CustomerOperationService
from ltc.modules.customer_operation.infrastructure.postgres_repository import (
    PostgresCustomerOperationRepository,
)


def build_operation_service() -> CustomerOperationService:
    return CustomerOperationService(repository=PostgresCustomerOperationRepository())





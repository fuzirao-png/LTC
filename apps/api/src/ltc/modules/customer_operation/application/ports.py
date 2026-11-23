from typing import Any, Protocol
from uuid import UUID


class CustomerOperationRepositoryPort(Protocol):
    def can_sales_access_company(self, company_id: str, sales_user_id: str) -> bool:
        """Return whether the salesperson owns or is assigned to the company."""

    def get_customer_operations(self, company_id: UUID, sales_user_id: str | None = None) -> dict | None:
        """Return the customer operation read model for a company."""

    def company_exists(self, company_id: str) -> bool:
        """Return whether a company exists in the operation store."""

    def list_activities(self, company_id: str, sales_user_id: str | None = None) -> list[Any]:
        """Return timeline activity records for a company."""

    def list_tasks(self, company_id: str, sales_user_id: str | None = None) -> list[Any]:
        """Return follow-up task records for a company."""

    def list_emails(self, company_id: str, sales_user_id: str | None = None) -> list[Any]:
        """Return email records, optionally scoped to their owning salesperson."""

    def get_email_attachment(self, *, company_id: str, email_id: str, attachment_id: str, sales_user_id: str | None = None) -> dict[str, Any] | None:
        """Return authorized attachment metadata."""


class AnalysisRunResult(Protocol):
    run_id: UUID
    status: str


class AnalysisTriggerPort(Protocol):
    """Port for triggering customer analysis from operations (PRD §5.1).

    Implemented by customer_analysis module via set_analysis_service().
    """

    def get_profile(self, company_id: UUID) -> Any: ...

    def update_profile(self, company_id: UUID, updates: dict, *, expected_version: int, updated_by: Any) -> None: ...

    def get_meddpicc(self, company_id: UUID) -> list[Any]: ...

    def update_meddpicc(
        self,
        company_id: UUID,
        dimension_code: str,
        *,
        expected_version: int,
        status: str,
        summary: str | None,
        payload: dict[str, Any] | None,
        level: str | None = None,
        updated_by: UUID | None = None,
    ) -> Any: ...

    def request_analysis(
        self,
        company_id: UUID,
        *,
        trigger_type: str,
        trigger_context: dict[str, Any] | None = None,
    ) -> AnalysisRunResult: ...


class EmailGeneratorPort(Protocol):
    async def generate_email(self, context: dict) -> dict:
        """Generate an editable email draft."""


class ASRPort(Protocol):
    async def transcribe(self, audio_path: str) -> dict:
        """Transcribe an uploaded meeting recording."""


class DeliveryPort(Protocol):
    async def send_email(self, payload: dict) -> dict:
        """Send an email through the configured provider."""





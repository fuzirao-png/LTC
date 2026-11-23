"""Sales CRM infrastructure layer."""

from ltc.modules.sales_crm.infrastructure.departure_repository import PostgresSalesDeparturePort
from ltc.modules.sales_crm.infrastructure.pool_repository import PostgresSalesPoolRepository

__all__ = ("PostgresSalesDeparturePort", "PostgresSalesPoolRepository")

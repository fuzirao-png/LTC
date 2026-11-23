"""Composition root for the lead-intelligence module."""

from .pipeline import LeadSearchPipeline
from ..infrastructure.llm import ChineseLanguageModel
from ..infrastructure.memory import MarkdownMemory
from ..infrastructure.postgres_repository import PostgresLeadRepository
from ..infrastructure.providers import ApifyLeadsFinderProvider, ApifyLinkedInProvider, ExaHttpProvider


def build_lead_search_pipeline() -> LeadSearchPipeline:
    return LeadSearchPipeline(
        memory=MarkdownMemory(),
        exa=ExaHttpProvider(),
        leads_finder=ApifyLeadsFinderProvider(),
        linkedin=ApifyLinkedInProvider(),
        llm=ChineseLanguageModel(),
        repository=PostgresLeadRepository(),
    )

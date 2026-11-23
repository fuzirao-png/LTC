import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "ltc" / "modules" / "customer_operation"
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def test_customer_operation_module_has_four_layer_skeleton() -> None:
    expected_files = [
        "interfaces/router.py",
        "interfaces/schemas.py",
        "application/service.py",
        "application/ports.py",
        "domain/email_message.py",
        "domain/meeting.py",
        "domain/follow_up_task.py",
        "domain/errors.py",
        "infrastructure/postgres_repository.py",
        "infrastructure/email_context_builder.py",
        "infrastructure/llm_adapter.py",
        "infrastructure/email_provider_adapter.py",
        "infrastructure/asr_adapter.py",
        "infrastructure/bootstrap.py",
    ]

    for relative_path in expected_files:
        assert (ROOT / relative_path).exists(), relative_path


def test_customer_operation_module_skeleton_imports() -> None:
    modules = [
        "ltc.modules.customer_operation.interfaces.router",
        "ltc.modules.customer_operation.interfaces.schemas",
        "ltc.modules.customer_operation.application.service",
        "ltc.modules.customer_operation.application.ports",
        "ltc.modules.customer_operation.domain.email_message",
        "ltc.modules.customer_operation.domain.meeting",
        "ltc.modules.customer_operation.domain.follow_up_task",
        "ltc.modules.customer_operation.domain.errors",
        "ltc.modules.customer_operation.infrastructure.postgres_repository",
        "ltc.modules.customer_operation.infrastructure.email_context_builder",
        "ltc.modules.customer_operation.infrastructure.llm_adapter",
        "ltc.modules.customer_operation.infrastructure.email_provider_adapter",
        "ltc.modules.customer_operation.infrastructure.asr_adapter",
        "ltc.modules.customer_operation.infrastructure.bootstrap",
    ]

    for module in modules:
        importlib.import_module(module)

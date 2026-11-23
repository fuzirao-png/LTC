from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import ltc.platform.config as config_module
from ltc.platform.config import get_settings


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_settings_default_to_v36_local_bind(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()

            settings = get_settings()

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8000)

    def test_settings_read_ltc_api_bind_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LTC_API_HOST": "0.0.0.0",
                "LTC_API_PORT": "9000",
            },
            clear=True,
        ):
            get_settings.cache_clear()

            settings = get_settings()

        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 9000)

    def test_openai_compatible_environment_configures_shared_llm(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_BASE_URL": "https://api.aicodemirror.ai/api/codex/backend-api/codex/v1",
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_MODEL": "gpt-5.6-terra",
                },
                clear=True,
            ),
            patch.object(config_module, "_env_file_candidates", return_value=()),
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(
            settings.llm_base_url,
            "https://api.aicodemirror.ai/api/codex/backend-api/codex/v1",
        )
        self.assertEqual(settings.llm_api_key, "test-key")
        self.assertEqual(settings.llm_model, "gpt-5.6-terra")

    def test_ltc_llm_variables_override_openai_compatible_defaults(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_BASE_URL": "https://provider.example/v1",
                    "OPENAI_API_KEY": "openai-key",
                    "OPENAI_MODEL": "openai-model",
                    "LTC_LLM_BASE_URL": "https://ltc.example/v1",
                    "LTC_LLM_API_KEY": "ltc-key",
                    "LTC_LLM_MODEL": "ltc-model",
                },
                clear=True,
            ),
            patch.object(config_module, "_env_file_candidates", return_value=()),
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.llm_base_url, "https://ltc.example/v1")
        self.assertEqual(settings.llm_api_key, "ltc-key")
        self.assertEqual(settings.llm_model, "ltc-model")

    def test_settings_build_database_dsn_from_ltc_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LTC_DB_HOST": "postgres",
                "LTC_DB_PORT": "5432",
                "LTC_DB_NAME": "ltc_test",
                "LTC_DB_USER": "api",
                "LTC_DB_PASSWORD": "contains space",
                "LTC_DB_SSLMODE": "disable",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(
            settings.database_dsn,
            "postgresql://api:contains%20space@postgres:5432/ltc_test?sslmode=disable",
        )

    def test_env_file_candidates_include_repository_root(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            api_directory = repository_root / "apps" / "api"
            config_file = api_directory / "src" / "ltc" / "platform" / "config.py"
            api_directory.mkdir(parents=True)
            config_file.parent.mkdir(parents=True)
            (repository_root / "compose.yaml").touch()

            candidates = config_module._env_file_candidates(
                cwd=api_directory,
                module_file=config_file,
            )

        self.assertEqual(
            tuple(candidate.resolve() for candidate in candidates),
            (
                (api_directory / ".env").resolve(),
                (repository_root / ".env").resolve(),
            ),
        )

    def test_settings_read_repository_env_when_started_from_api_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            api_directory = repository_root / "apps" / "api"
            config_file = api_directory / "src" / "ltc" / "platform" / "config.py"
            api_directory.mkdir(parents=True)
            config_file.parent.mkdir(parents=True)
            (repository_root / "compose.yaml").touch()
            (repository_root / ".env").write_text(
                "INBOUND_MAIL_ENABLED=true\n"
                "INBOUND_MAIL_USERNAME=mailbox@example.com\n"
                "INBOUND_MAIL_PASSWORD=secret\n",
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(config_module, "__file__", str(config_file)),
                patch.object(config_module.Path, "cwd", return_value=api_directory),
            ):
                get_settings.cache_clear()
                settings = get_settings()

        self.assertTrue(settings.inbound_mail_enabled)
        self.assertEqual(settings.inbound_mail_username, "mailbox@example.com")
        self.assertEqual(settings.inbound_mail_password, "secret")


if __name__ == "__main__":
    unittest.main()

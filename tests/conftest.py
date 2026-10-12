"""Global pytest configuration for PlanForge AI test suite."""

import os
import pytest


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Ensure tests run offline with mock provider by default unless explicitly configured."""
    if os.environ.get("PLANFORGE_LIVE_NETWORK_TESTS") != "1":
        monkeypatch.setenv("PLANFORGE_LLM_PROVIDER", "mock")

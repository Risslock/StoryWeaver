"""Unit tests for hybrid-search settings on core.config.Settings (feature 014)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestHybridSearchDefaults:
    """Default Settings() must instantiate with hybrid search off and equal weights."""

    def test_defaults(self) -> None:
        from core.config import Settings

        env_without_overrides = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("HYBRID_SEARCH_")
        }
        with patch.dict(os.environ, env_without_overrides, clear=True):
            s = Settings()

        assert s.hybrid_search_enabled is False
        assert s.hybrid_search_keyword_weight == 1.0
        assert s.hybrid_search_vector_weight == 1.0


class TestHybridSearchWeightValidation:
    """Non-positive weights must raise ValueError at Settings() construction time."""

    def test_zero_keyword_weight_raises(self) -> None:
        from core.config import Settings

        with (
            patch.dict(os.environ, {"HYBRID_SEARCH_KEYWORD_WEIGHT": "0"}),
            pytest.raises(ValueError, match="HYBRID_SEARCH_KEYWORD_WEIGHT must be > 0.0"),
        ):
            Settings()

    def test_negative_vector_weight_raises(self) -> None:
        from core.config import Settings

        with (
            patch.dict(os.environ, {"HYBRID_SEARCH_VECTOR_WEIGHT": "-1"}),
            pytest.raises(ValueError, match="HYBRID_SEARCH_VECTOR_WEIGHT must be > 0.0"),
        ):
            Settings()

    def test_valid_override_accepted(self) -> None:
        from core.config import Settings

        with patch.dict(os.environ, {"HYBRID_SEARCH_KEYWORD_WEIGHT": "1.5"}):
            s = Settings()

        assert s.hybrid_search_keyword_weight == 1.5

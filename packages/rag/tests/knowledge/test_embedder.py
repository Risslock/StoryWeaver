"""Unit tests for OllamaEmbedFn — verifies ChromaDB compatibility and model consistency."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestOllamaEmbedFnName:
    """OllamaEmbedFn must expose a `name` property that ChromaDB uses to tag collections."""

    def test_name_property_exists(self) -> None:
        from rag.knowledge.embedder import OllamaEmbedFn

        fn = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
        assert hasattr(fn, "name"), "OllamaEmbedFn must have a `name` attribute for ChromaDB"

    def test_name_includes_model(self) -> None:
        from rag.knowledge.embedder import OllamaEmbedFn

        fn = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
        assert "nomic-embed-text" in fn.name

    def test_same_model_same_name(self) -> None:
        """Two instances with the same model must share the same name — ChromaDB consistency."""
        from rag.knowledge.embedder import OllamaEmbedFn

        fn1 = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
        fn2 = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
        assert fn1.name == fn2.name

    def test_different_models_different_names(self) -> None:
        """Different models must produce different names so ChromaDB detects mismatch."""
        from rag.knowledge.embedder import OllamaEmbedFn

        fn_a = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
        fn_b = OllamaEmbedFn(model="mxbai-embed-large", base_url="http://localhost:11434")
        assert fn_a.name != fn_b.name


class TestGetEmbedFnConsistency:
    """`get_embed_fn()` must read model from env/settings so ingestion and retrieval agree."""

    def test_reads_model_from_env(self) -> None:
        from rag.knowledge.embedder import get_embed_fn

        with patch.dict(os.environ, {"KNOWLEDGE_EMBED_MODEL": "custom-model-xyz"}):
            fn = get_embed_fn()
        assert "custom-model-xyz" in fn.name

    def test_default_model_is_nomic(self) -> None:
        """When no env override is set the default should be nomic-embed-text."""
        from core.config import settings
        from rag.knowledge.embedder import get_embed_fn

        env_without_override = {k: v for k, v in os.environ.items() if k != "KNOWLEDGE_EMBED_MODEL"}
        with patch.dict(os.environ, env_without_override, clear=True):
            fn = get_embed_fn()
        assert settings.knowledge_embed_model in fn.name

    def test_two_calls_same_env_same_name(self) -> None:
        """Two consecutive get_embed_fn() calls with the same env must produce the same name."""
        from rag.knowledge.embedder import get_embed_fn

        with patch.dict(os.environ, {"KNOWLEDGE_EMBED_MODEL": "nomic-embed-text"}):
            fn1 = get_embed_fn()
            fn2 = get_embed_fn()
        assert fn1.name == fn2.name


class TestOllamaEmbedFnIsCallable:
    """OllamaEmbedFn.__call__ must call the Ollama API and return embeddings."""

    def test_call_returns_embeddings(self) -> None:
        import json
        import urllib.request
        from unittest.mock import patch

        from rag.knowledge.embedder import OllamaEmbedFn

        fake_response_body = json.dumps({"embeddings": [[0.1, 0.2, 0.3]]}).encode()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = fake_response_body

        with patch("urllib.request.urlopen", return_value=mock_resp):
            fn = OllamaEmbedFn(model="nomic-embed-text", base_url="http://localhost:11434")
            result = fn(["hello world"])

        assert result == [[0.1, 0.2, 0.3]]

    def test_call_raises_provider_unavailable_on_error(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from core.errors import ProviderUnavailableError
        from rag.knowledge.embedder import OllamaEmbedFn

        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            fn = OllamaEmbedFn(model="nomic-embed-text", base_url="http://127.0.0.1:9")
            with pytest.raises(ProviderUnavailableError):
                fn(["hello"])

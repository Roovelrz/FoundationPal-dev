"""Embedding backends for deterministic tests and local BGE retrieval."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Literal, cast

_HASH_DIM = 32
_BGE_DEFAULT_PATH = Path(__file__).resolve().parents[2] / 'models' / 'bge-base-zh-v1.5'


class EmbeddingService:
    _instance: EmbeddingService | None = None
    _lock = Lock()

    def __init__(self) -> None:
        configured = os.getenv('EMBEDDING_BACKEND', 'hash').lower()
        if configured not in ('hash', 'bge'):
            raise RuntimeError(f'unsupported_embedding_backend: {configured}')
        self.backend = cast(Literal['hash', 'bge'], configured)
        self.model_name = 'placeholder-hash-v1'
        self.model_revision = 'v1'
        self.dim = _HASH_DIM
        self._model: Any | None = None
        if self.backend == 'bge':
            self._load_bge()

    def _load_bge(self) -> None:
        model_path = Path(os.getenv('BGE_MODEL_PATH', str(_BGE_DEFAULT_PATH)))
        if not model_path.is_dir() or not any(model_path.glob('pytorch_model.*')) and not any(model_path.glob('model.safetensors')):
            raise RuntimeError(f'embedding_model_weights_missing: {model_path}')
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(str(model_path), local_files_only=True)
            self.model_name = model_path.name
            self.model_revision = 'local'
            dimension = getattr(self._model, 'get_embedding_dimension', self._model.get_sentence_embedding_dimension)
            self.dim = int(dimension())
        except Exception as exc:
            raise RuntimeError(f'embedding_model_initialization_failed: {model_path}') from exc

    @classmethod
    def instance(cls) -> EmbeddingService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        if self.backend == 'bge':
            vectors = self._model.encode(items, normalize_embeddings=True, show_progress_bar=False)
            return [[float(value) for value in vector] for vector in vectors]
        return [[value / 255.0 for value in hashlib.sha256(text.encode('utf-8')).digest()[:self.dim]] for text in items]

    def health(self) -> dict[str, Any]:
        return {
            'backend': self.backend,
            'model': self.model_name,
            'revision': self.model_revision,
            'dim': self.dim,
            'ready': self._model is not None if self.backend == 'bge' else True,
        }


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    return EmbeddingService.instance().embed(texts)

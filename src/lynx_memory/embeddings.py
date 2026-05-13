"""Embedding client — supports Voyage AI and OpenAI backends.

Backend is controlled by the EMBEDDING_BACKEND env var: "voyage" (default) | "openai".
"""
import os
from functools import lru_cache
from typing import List

from .config import load_env

load_env()

_DEFAULT_VOYAGE_MODEL = "voyage-3.5"
_DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"


def _backend() -> str:
    return os.environ.get("EMBEDDING_BACKEND", "voyage").strip().lower()


@lru_cache(maxsize=1)
def _voyage_client():
    import voyageai
    key = os.environ.get("VOYAGE_API_KEY")
    if not key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    return voyageai.Client(api_key=key)


@lru_cache(maxsize=1)
def _openai_client():
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key, base_url=base_url)


def embed(texts: List[str], input_type: str = "document") -> List[List[float]]:
    if not texts:
        return []
    backend = _backend()
    if backend == "voyage":
        model = os.environ.get("VOYAGE_MODEL", _DEFAULT_VOYAGE_MODEL)
        resp = _voyage_client().embed(texts, model=model, input_type=input_type)
        return resp.embeddings
    else:
        model = os.environ.get("OPENAI_EMBEDDING_MODEL", _DEFAULT_OPENAI_EMBEDDING_MODEL)
        resp = _openai_client().embeddings.create(input=texts, model=model)
        return [d.embedding for d in resp.data]


def embed_one(text: str, input_type: str = "document") -> List[float]:
    return embed([text], input_type=input_type)[0]

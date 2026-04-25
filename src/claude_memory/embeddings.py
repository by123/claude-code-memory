"""Voyage AI embedding client."""
import os
from functools import lru_cache
from typing import List

import voyageai

from .config import load_env

load_env()

MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3")


@lru_cache(maxsize=1)
def _client() -> voyageai.Client:
    key = os.environ.get("VOYAGE_API_KEY")
    if not key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    return voyageai.Client(api_key=key)


def embed(texts: List[str], input_type: str = "document") -> List[List[float]]:
    if not texts:
        return []
    resp = _client().embed(texts, model=MODEL, input_type=input_type)
    return resp.embeddings


def embed_one(text: str, input_type: str = "document") -> List[float]:
    return embed([text], input_type=input_type)[0]

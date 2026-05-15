"""Voyage AI embeddings client.

We use voyage-3.5-lite at 1024 dimensions. Cheap, fast, plenty good for
personal-scale memory retrieval.

Why two functions (document vs query): Voyage's models are trained to map
"questions you might ask" and "things you might find" into the same space —
but only if you tell them which is which via the `input_type` parameter.
Mismatching them costs accuracy.
"""

from functools import lru_cache

import voyageai

from app.config import settings

EMBED_MODEL = "voyage-3.5-lite"
EMBED_DIM = 1024


@lru_cache(maxsize=1)
def _client() -> voyageai.AsyncClient:
    return voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)


async def embed_document(text: str) -> list[float]:
    """Embed a fact we're storing (a memory)."""
    result = await _client().embed(
        texts=[text],
        model=EMBED_MODEL,
        input_type="document",
        output_dimension=EMBED_DIM,
    )
    return result.embeddings[0]


async def embed_query(text: str) -> list[float]:
    """Embed a user message we're using to search memories."""
    result = await _client().embed(
        texts=[text],
        model=EMBED_MODEL,
        input_type="query",
        output_dimension=EMBED_DIM,
    )
    return result.embeddings[0]

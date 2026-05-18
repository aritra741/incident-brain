import google.generativeai as genai
from typing import List
import logging
import hashlib
import math
import random

from ..config import settings

logger = logging.getLogger(__name__)

EMBEDDING_PROMPT_TEMPLATE = """Generate a semantic embedding for the following incident event text.
Focus on the technical content, actions taken, and outcomes described.

Text: {text}"""


class EmbeddingService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._logged_fallback_warning = False

    async def get_embedding(self, text: str) -> List[float]:
        try:
            result = genai.embed_content(
                model="gemini-embedding-exp-03-07",
                content=text,
                task_type="retrieval_document",
            )
            return self._normalize_embedding(result["embedding"])
        except Exception as e:
            self._log_fallback_once(e)
            return self._deterministic_embedding(text)

    async def get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            embeddings = []
            for text in texts:
                embedding = await self.get_embedding(text)
                embeddings.append(embedding)
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            return [self._get_zero_embedding() for _ in texts]

    def _get_zero_embedding(self) -> List[float]:
        return [0.0] * settings.EMBEDDING_DIMENSION

    def _normalize_embedding(self, embedding: List[float]) -> List[float]:
        if not isinstance(embedding, list):
            return self._get_zero_embedding()

        target = settings.EMBEDDING_DIMENSION
        if len(embedding) == target:
            return embedding
        if len(embedding) > target:
            return embedding[:target]
        return embedding + ([0.0] * (target - len(embedding)))

    def _deterministic_embedding(self, text: str) -> List[float]:
        target = settings.EMBEDDING_DIMENSION
        if not text:
            return self._get_zero_embedding()

        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(target)]

        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return self._get_zero_embedding()
        return [x / norm for x in vector]

    def _log_fallback_once(self, error: Exception) -> None:
        if self._logged_fallback_warning:
            return
        self._logged_fallback_warning = True
        logger.warning(
            "Embedding API unavailable (%s). Falling back to deterministic local embeddings.",
            str(error),
        )

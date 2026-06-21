class Embedder:
    _instance = None

    @classmethod
    def get(cls) -> "Embedder":
        """Singleton — load model once, reuse."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(
                "nomic-ai/nomic-embed-text-v1",
                trust_remote_code=True,
                cache_folder="./models"
            )
        except Exception as e:
            print(f"Failed to initialize SentenceTransformer: {e}. Using mock embedder fallback.")
            self.model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        if self.model is None:
            # Return mock 768-dimensional vectors
            return [[0.0] * 768 for _ in texts]
        try:
            prefixed = [f"search_document: {t}" for t in texts]
            return self.model.encode(prefixed, normalize_embeddings=True).tolist()
        except Exception as e:
            print(f"Error during embedding: {e}. Falling back to mock embeddings.")
            return [[0.0] * 768 for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query (different prefix for asymmetric search)."""
        if self.model is None:
            return [0.0] * 768
        try:
            prefixed = f"search_query: {query}"
            return self.model.encode([prefixed], normalize_embeddings=True)[0].tolist()
        except Exception as e:
            print(f"Error during query embedding: {e}. Falling back to mock query embedding.")
            return [0.0] * 768


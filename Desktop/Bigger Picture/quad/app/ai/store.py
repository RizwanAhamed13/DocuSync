class VectorStore:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            import chromadb
            cls._client = chromadb.PersistentClient(path="./chroma_db")
        return cls._client

    @classmethod
    def get_collection(cls, app_name: str):
        """
        Get or create a ChromaDB collection for this app.
        Collection name: "quad-{sanitized_app_name}"
        Use cosine distance.
        """
        client = cls.get_client()
        from app.builder import sanitize_app_name
        return client.get_or_create_collection(
            name=f"quad-{sanitize_app_name(app_name)}",
            metadata={"hnsw:space": "cosine"}
        )

    @classmethod
    def upsert_chunks(cls, app_name: str,
                      chunk_ids: list[str],
                      embeddings: list[list[float]],
                      documents: list[str],
                      metadatas: list[dict]) -> None:
        col = cls.get_collection(app_name)
        col.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    @classmethod
    def search(cls, app_name: str,
               query_embedding: list[float],
               n_results: int = 8) -> list[dict]:
        """
        Search for the n_results most relevant chunks.
        Returns list of:
        { chunk_id, document, metadata, distance }
        Returns [] if collection does not exist.
        """
        try:
            col = cls.get_collection(app_name)
            results = col.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            out = []
            if not results or not results.get("ids") or len(results["ids"]) == 0:
                return []
            for i in range(len(results["ids"][0])):
                out.append({
                    "chunk_id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
            return out
        except Exception:
            return []

    @classmethod
    def delete_collection(cls, app_name: str) -> None:
        """Delete all vectors for an app (called on app deletion)."""
        try:
            from app.builder import sanitize_app_name
            cls.get_client().delete_collection(
                f"quad-{sanitize_app_name(app_name)}"
            )
        except Exception:
            pass

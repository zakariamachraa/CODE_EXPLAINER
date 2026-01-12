from __future__ import annotations

import json
from pathlib import Path
from typing import List, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer


class LocalVectorDB:
    def __init__(self, data_path: Path, embedder_name: str) -> None:
        self.data_path = Path(data_path)
        self.embedder_name = embedder_name
        self.model = SentenceTransformer(embedder_name)
        self.entries: list[dict] = []
        self.embeddings: np.ndarray | None = None

    def load(self) -> None:
        if not self.data_path.exists():
            raise FileNotFoundError(f"Missing knowledge base at {self.data_path}")
        with self.data_path.open("r", encoding="utf-8") as fh:
            self.entries = json.load(fh)
        self._recompute_embeddings()

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not self.entries:
            return []
        query_vec = self.model.encode([query], normalize_embeddings=True)[0]
        scores = np.dot(self.embeddings, query_vec)
        indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in indices:
            item = self.entries[idx].copy()
            item["score"] = float(scores[idx])
            results.append(item)
        return results

    def add_entry(self, entry: dict) -> None:
        entry["id"] = entry.get("id") or f"{entry['language']}-{len(self.entries)+1}"
        self.entries.append(entry)
        self._persist()
        self._recompute_embeddings()

    def _persist(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        with self.data_path.open("w", encoding="utf-8") as fh:
            json.dump(self.entries, fh, indent=2, ensure_ascii=False)

    def _recompute_embeddings(self) -> None:
        if not self.entries:
            self.embeddings = np.zeros((0, 384))
            return
        corpus = [self._entry_text(entry) for entry in self.entries]
        self.embeddings = self.model.encode(corpus, normalize_embeddings=True)

    @staticmethod
    def _entry_text(entry: dict) -> str:
        parts: Sequence[str] = [
            entry.get("language", ""),
            entry.get("title", ""),
            entry.get("code_fragment", ""),
            entry.get("explanation", ""),
            " ".join(entry.get("tags", [])),
        ]
        return " ".join(part for part in parts if part).strip()
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from google.cloud import storage


@dataclass(frozen=True)
class Part:
    part_id: str
    name: str
    description: str
    compatible_with: tuple[str, ...]
    source_id: str
    catalog_version: str

    @property
    def searchable_text(self) -> str:
        return " ".join((self.part_id, self.name, self.description, *self.compatible_with)).lower()


class Catalog:
    def __init__(self, parts: list[Part], loaded_at: datetime | None = None):
        self.parts = parts
        self.loaded_at = loaded_at or datetime.now(UTC)
        self.version = max(part.catalog_version for part in parts)

    @classmethod
    def from_json(cls, raw: str) -> "Catalog":
        payload = json.loads(raw)
        return cls([Part(
            part_id=item["part_id"], name=item["name"], description=item["description"],
            compatible_with=tuple(item["compatible_with"]), source_id=item["source_id"],
            catalog_version=item["catalog_version"],
        ) for item in payload["parts"] if not item.get("deleted", False)])

    @classmethod
    def load(cls, local_path: str, gcs_uri: str | None = None) -> "Catalog":
        if not gcs_uri:
            return cls.from_json(Path(local_path).read_text(encoding="utf-8"))
        parsed = urlparse(gcs_uri)
        raw = storage.Client().bucket(parsed.netloc).blob(parsed.path.lstrip("/")).download_as_text()
        return cls.from_json(raw)

    def search(self, query: str, limit: int) -> list[Part]:
        terms = {term.lower() for term in query.split() if len(term) > 2}
        ranked = sorted(
            ((sum(term in part.searchable_text for term in terms), part) for part in self.parts),
            key=lambda pair: (pair[0], pair[1].part_id), reverse=True,
        )
        return [part for score, part in ranked if score > 0][:limit]

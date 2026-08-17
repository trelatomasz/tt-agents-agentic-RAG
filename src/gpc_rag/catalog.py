import json
import re
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


@dataclass(frozen=True)
class SearchHit:
    part: Part
    score: float
    matched_terms: tuple[str, ...]

    @property
    def confidence(self) -> float:
        return min(1.0, self.score / 10.0)


_TOKEN = re.compile(r"[a-z0-9]+")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "does",
    "fit",
    "fits",
    "for",
    "is",
    "part",
    "the",
    "which",
}


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower())) - _STOP_WORDS


def _years(value: str) -> set[int]:
    return {int(year) for year in _YEAR.findall(value)}


def _compatible_years(fitment: str, requested_years: set[int]) -> bool:
    if not requested_years:
        return True
    fitment_years = sorted(_years(fitment))
    if len(fitment_years) >= 2:
        start, end = fitment_years[0], fitment_years[-1]
        return any(start <= year <= end for year in requested_years)
    return bool(fitment_years) and any(year in fitment_years for year in requested_years)


class Catalog:
    def __init__(self, parts: list[Part], loaded_at: datetime | None = None):
        if not parts:
            raise ValueError("catalog must contain at least one active part")
        self.parts = parts
        self.loaded_at = loaded_at or datetime.now(UTC)
        self.version = max(part.catalog_version for part in parts)

    @classmethod
    def from_json(cls, raw: str) -> "Catalog":
        payload = json.loads(raw)
        return cls(
            [
                Part(
                    part_id=item["part_id"],
                    name=item["name"],
                    description=item["description"],
                    compatible_with=tuple(item["compatible_with"]),
                    source_id=item["source_id"],
                    catalog_version=item["catalog_version"],
                )
                for item in payload["parts"]
                if not item.get("deleted", False)
            ]
        )

    @classmethod
    def load(cls, local_path: str, gcs_uri: str | None = None) -> "Catalog":
        if not gcs_uri:
            return cls.from_json(Path(local_path).read_text(encoding="utf-8"))
        parsed = urlparse(gcs_uri)
        raw = (
            storage.Client().bucket(parsed.netloc).blob(parsed.path.lstrip("/")).download_as_text()
        )
        return cls.from_json(raw)

    def search(self, query: str, limit: int, min_score: float = 2.0) -> list[SearchHit]:
        """Return evidence matching both the product and requested fitment."""
        query_terms = _tokens(query)
        requested_years = _years(query)
        vehicle_terms = {
            token
            for part in self.parts
            for fitment in part.compatible_with
            for token in _tokens(fitment)
            if not token.isdigit()
        }
        requested_vehicle_terms = query_terms & vehicle_terms
        requested_year_tokens = {str(year) for year in requested_years}
        requested_part_ids = {
            part.part_id for part in self.parts if _tokens(part.part_id) <= query_terms
        }
        ranked: list[SearchHit] = []

        for part in self.parts:
            if requested_part_ids and part.part_id not in requested_part_ids:
                continue
            part_terms = _tokens(part.searchable_text)
            lexical_terms = query_terms & part_terms
            compatibility_overlap: set[str] = set()
            compatibility_score = 0.0
            for fitment in part.compatible_with:
                fitment_terms = _tokens(fitment)
                overlap = (query_terms & fitment_terms) - requested_year_tokens
                if requested_vehicle_terms and not overlap:
                    continue
                if not _compatible_years(fitment, requested_years):
                    continue
                if overlap:
                    compatibility_overlap.update(overlap)
                    compatibility_score = max(compatibility_score, len(overlap) * 3.0)
                    fitment_model = _YEAR.sub("", fitment).lower()
                    if _tokens(fitment_model) <= query_terms:
                        compatibility_score += 2.0

            if requested_vehicle_terms and not compatibility_overlap:
                continue
            score = float(len(lexical_terms)) + compatibility_score
            if score >= min_score:
                ranked.append(
                    SearchHit(part, score, tuple(sorted(lexical_terms | compatibility_overlap)))
                )

        ranked.sort(key=lambda hit: (-hit.score, hit.part.part_id))
        return ranked[:limit]

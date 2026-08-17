"""The one contract every connector implements (specification section 5).

An adapter must not know whether the index is PostgreSQL, a vector service or the
in-process test double. Normalization, chunking, embedding and index writes belong to the
pipeline, so a new source costs an adapter and nothing else.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from ..models import DiscoveryRequest, ItemStatus, RawDocument, SourceDescriptor, SourceItem


class AdapterError(RuntimeError):
    """A source-specific failure for one item.

    The pipeline records the carried `status` and continues. Deletion is deliberately not
    expressible here: section 7 requires that an adapter error is never interpreted as a
    delete, so a removal must be proven by a `SourceItem` with `status="deleted"`.
    """

    def __init__(self, message: str, *, item_id: str, status: ItemStatus = "unreadable"):
        if status in ("available", "deleted"):
            raise ValueError(f"{status!r} is not a failure status; report it from discover()")
        super().__init__(message)
        self.item_id = item_id
        self.status = status


@runtime_checkable
class SourceAdapter(Protocol):
    source_type: str
    adapter_version: str

    def discover(self, request: DiscoveryRequest) -> Iterable[SourceItem]:
        """Enumerate candidate items, honoring `changed_only` and `known_revisions`."""
        ...

    def fetch(self, item: SourceItem) -> RawDocument:
        """Retrieve and parse one item, or raise `AdapterError` describing the failure."""
        ...

    def fingerprint(self, document: RawDocument) -> str:
        """Identify fetched content so an unchanged re-fetch can skip the pipeline."""
        ...


def load_descriptor(path: str | Path) -> SourceDescriptor:
    """Load a section 5 descriptor from YAML or JSON.

    Descriptors are configuration, not content: they are read from the operator's
    filesystem and are never produced by a source or a model.
    """
    location = Path(path)
    raw = location.read_text(encoding="utf-8")
    if location.suffix.lower() in (".yaml", ".yml"):
        import yaml  # imported lazily so JSON-only callers do not pay for the parser

        payload: Any = yaml.safe_load(raw)
    else:
        payload = json.loads(raw)
    try:
        return SourceDescriptor.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{location} is not a valid source descriptor: {exc}") from exc

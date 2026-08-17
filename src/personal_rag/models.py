"""Canonical contracts for the personal RAG platform (specification sections 5, 6 and 9).

Every source adapter emits these records, so the query boundary never learns which source
format produced a chunk. Three field names differ from the specification prose because the
storage encoding is a Phase 3 concern rather than a contract concern:

| Specification      | Contract field   | Reason                                     |
|--------------------|------------------|--------------------------------------------|
| `locator_json`     | `locator`        | Typed `Locator`; JSON is a column encoding |
| `lexical_text_vector` | `lexical_terms` | A PostgreSQL `tsvector` is index-specific  |
| `metadata_json`    | `metadata_json`  | Kept verbatim; it really is opaque JSON    |
"""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Visibility = Literal["private", "shared", "public"]
RefreshPolicy = Literal["manual", "scheduled", "on_commit", "event_driven"]
RightsPolicy = Literal["personal_reference", "owner_approved", "public_domain", "restricted"]
SourceType = Literal["filesystem", "web", "git_tree", "repository_ci"]
DocumentStatus = Literal["active", "deleted", "quarantined", "rejected"]
ItemStatus = Literal["available", "deleted", "unreadable", "unsupported", "quarantined"]
RunStatus = Literal["running", "staged", "succeeded", "failed", "quarantined"]

# Storage and model processing require an approving rights policy (section 10). A source
# whose rights are unresolved must use `restricted` and stay out of the index.
_RIGHTS_PERMISSIONS: dict[str, tuple[bool, bool]] = {
    "personal_reference": (True, True),
    "owner_approved": (True, True),
    "public_domain": (True, True),
    "restricted": (False, False),
}


def content_hash(text: str) -> str:
    """Hash normalized content; this identifies a document *version*, not a document."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def build_chunk_id(document_id: str, document_version_hash: str, ordinal: int) -> str:
    """Stable across re-ingestion of identical content, distinct across versions."""
    return f"{document_id}@{document_version_hash[:12]}#{ordinal:04d}"


class SourceDescriptor(BaseModel):
    """Section 5 descriptor. Adapter-specific keys fold into `configuration` on load."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    source_type: SourceType
    display_name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    rights_policy: RightsPolicy
    visibility: Visibility = "private"
    refresh_policy: RefreshPolicy = "manual"
    adapter_version: str = "unversioned"
    configuration: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fold_adapter_configuration(cls, data: Any) -> Any:
        """Keep the section 5 YAML example loadable: unknown keys are adapter settings."""
        if not isinstance(data, dict):
            return data
        known = set(cls.model_fields)
        configuration = dict(data.get("configuration") or {})
        configuration.update({key: value for key, value in data.items() if key not in known})
        folded = {key: value for key, value in data.items() if key in known}
        folded["configuration"] = configuration
        return folded

    @property
    def allows_storage(self) -> bool:
        return _RIGHTS_PERMISSIONS[self.rights_policy][0]

    @property
    def allows_model_processing(self) -> bool:
        return _RIGHTS_PERMISSIONS[self.rights_policy][1]

    @property
    def acl_labels(self) -> tuple[str, ...]:
        """Labels filtered before ranking; never derived from a client-supplied field."""
        labels = [f"source:{self.source_id}", f"owner:{self.owner}"]
        if self.visibility == "public":
            labels.append("public")
        elif self.visibility == "shared":
            labels.append(f"shared:{self.source_id}")
        return tuple(labels)


class Principal(BaseModel):
    """The authenticated caller. Grants come from server context, never from the request."""

    model_config = ConfigDict(frozen=True)

    subject: str = Field(min_length=1)
    grants: frozenset[str] = frozenset()

    @classmethod
    def owner(cls, subject: str) -> "Principal":
        """The single-owner default of section 14: own everything, plus public sources."""
        return cls(subject=subject, grants=frozenset({f"owner:{subject}", "public"}))

    def may_read(self, acl_labels: tuple[str, ...] | frozenset[str]) -> bool:
        return bool(self.grants & frozenset(acl_labels))


class Locator(BaseModel):
    """Whatever the source can prove about where a chunk came from (section 6)."""

    model_config = ConfigDict(frozen=True)

    path: str | None = None
    url: str | None = None
    commit: str | None = None
    page: int | None = None
    paragraph: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    fragment: str | None = None

    def human_reference(self, heading_path: tuple[str, ...] = ()) -> str:
        """A locator a human can follow back to the source without querying the index."""
        anchor = self.url or self.path or ""
        if self.page is not None:
            anchor = f"{anchor} p.{self.page}" if anchor else f"p.{self.page}"
        elif self.line_start is not None:
            span = f"{self.line_start}-{self.line_end}" if self.line_end else str(self.line_start)
            anchor = f"{anchor}:{span}" if anchor else f"line {span}"
        if self.commit:
            anchor = f"{anchor}@{self.commit[:8]}"
        heading = " > ".join(heading_path)
        return f"{anchor} § {heading}".strip() if heading else anchor.strip()


class SourceItem(BaseModel):
    """One discovered unit of source material, before any fetching or parsing."""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    status: ItemStatus = "available"
    title: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    source_revision: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def document_id(self) -> str:
        """Stable across content changes, so versions of one file stay one document."""
        return f"{self.source_id}:{self.item_id}"


class RawDocument(BaseModel):
    """Adapter output: source-specific parsing is finished, pipeline stages have not run."""

    model_config = ConfigDict(frozen=True)

    item: SourceItem
    text: str
    title: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    fetched_at: datetime
    published_at: datetime | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def document_id(self) -> str:
        return self.item.document_id


class DiscoveryRequest(BaseModel):
    """Input to `SourceAdapter.discover`; `known_revisions` drives incremental runs."""

    model_config = ConfigDict(frozen=True)

    descriptor: SourceDescriptor
    changed_only: bool = True
    known_revisions: dict[str, str] = Field(default_factory=dict)
    limit: int | None = Field(default=None, ge=1)


class DocumentVersion(BaseModel):
    """Section 6 document version. `content_hash` identifies this specific version."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    title: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    language: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    fetched_at: datetime
    published_at: datetime | None = None
    parser_version: str = Field(min_length=1)
    normalizer_version: str = Field(min_length=1)
    visibility: Visibility
    rights_policy: RightsPolicy
    status: DocumentStatus = "active"
    acl_labels: tuple[str, ...] = ()
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """Section 6 chunk: the unit that is embedded, retrieved, filtered and cited."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    document_version_hash: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    language: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    locator: Locator = Locator()
    acl_labels: tuple[str, ...] = ()
    lexical_terms: tuple[str, ...] = ()
    dense_embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    index_run_id: str | None = None


class Citation(BaseModel):
    """Evidence an agent can verify without database access (section 6)."""

    chunk_id: str
    document_id: str
    source_id: str
    source_uri: str
    title: str
    document_version_hash: str
    heading_path: tuple[str, ...] = ()
    locator: Locator = Locator()
    reference: str = ""

    @classmethod
    def from_chunk(cls, chunk: Chunk, version: DocumentVersion) -> "Citation":
        return cls(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            source_id=chunk.source_id,
            source_uri=version.source_uri,
            title=version.title,
            document_version_hash=chunk.document_version_hash,
            heading_path=chunk.heading_path,
            locator=chunk.locator,
            reference=chunk.locator.human_reference(chunk.heading_path) or version.source_uri,
        )


class SearchRequest(BaseModel):
    """`POST /v1/search` (section 9). `source_ids` narrows; it never grants access."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=3, max_length=1000)
    request_id: str = Field(min_length=3, max_length=100)
    principal: Principal
    source_ids: frozenset[str] = frozenset()
    top_k: int = Field(default=8, ge=1, le=50)


class SearchResult(BaseModel):
    """One ranked chunk with the retrieval signals that produced it."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float
    lexical_score: float = 0.0
    dense_score: float = 0.0
    lexical_rank: int | None = None
    dense_rank: int | None = None
    matched_terms: tuple[str, ...] = ()

    @property
    def supported(self) -> bool:
        """True when at least one retrieval signal actually fired for this chunk."""
        return bool(self.matched_terms) or self.dense_rank is not None


class SearchResponse(BaseModel):
    request_id: str
    results: list[SearchResult]
    index_run_id: str | None = None
    degraded: bool = False


class AnswerRequest(SearchRequest):
    """`POST /v1/answer` (section 9): search plus bounded generation over the evidence."""

    max_evidence_chunks: int = Field(default=6, ge=1, le=20)


class AnswerResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    index_run_id: str | None = None
    retrieval_score: float = Field(default=0.0, ge=0, le=1)
    degraded: bool = False


class IngestionRunCounters(BaseModel):
    discovered: int = 0
    fetched: int = 0
    skipped_unchanged: int = 0
    rejected: int = 0
    quarantined: int = 0
    documents_indexed: int = 0
    chunks_indexed: int = 0
    tombstoned: int = 0


class IngestionRunError(BaseModel):
    item_id: str
    stage: str
    code: str
    message: str


class IngestionRun(BaseModel):
    """Section 7 run record: the evidence that a specific index state was produced."""

    run_id: str
    source_id: str
    status: RunStatus = "running"
    started_at: datetime
    finished_at: datetime | None = None
    dry_run: bool = False
    adapter_version: str = "unversioned"
    parser_version: str = "unversioned"
    normalizer_version: str = "unversioned"
    chunker_version: str = "unversioned"
    embedding_model: str | None = None
    index_run_id: str | None = None
    counters: IngestionRunCounters = IngestionRunCounters()
    errors: list[IngestionRunError] = Field(default_factory=list)

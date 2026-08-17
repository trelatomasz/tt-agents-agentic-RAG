"""Typed failures shared by the ingestion and query boundaries."""


class PersonalRagError(RuntimeError):
    """Base class so callers can separate platform failures from programming errors."""


class NoEvidenceError(PersonalRagError):
    """Retrieval found nothing the principal may read that supports the query."""


class GroundingError(PersonalRagError):
    """The generated answer cited nothing, or cited evidence that was not retrieved."""


class DependencyFailedError(PersonalRagError):
    """An embedding, index or generation dependency failed; the caller may retry."""


class RightsViolationError(PersonalRagError):
    """Storage or model processing was attempted without an approving rights policy."""


class AccessDeniedError(PersonalRagError):
    """The principal is not permitted to read the requested source."""


class IngestionError(PersonalRagError):
    """An ingestion run could not complete; the active index must stay unchanged."""

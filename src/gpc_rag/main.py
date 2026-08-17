import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .catalog import Catalog
from .config import get_settings
from .generator import DeterministicGenerator, VertexGenerator
from .models import AskRequest, ErrorBody, ErrorResponse
from .service import (
    CatalogStaleError,
    DependencyFailedError,
    GroundingError,
    NoEvidenceError,
    RagService,
)

settings = get_settings()
catalog = Catalog.load(settings.catalog_path, settings.catalog_gcs_uri)
generator = (
    VertexGenerator(settings.project_id, settings.location, settings.model_id)
    if settings.use_vertex
    else DeterministicGenerator()
)
service = RagService(
    catalog,
    generator,
    settings.catalog_max_age_seconds,
    settings.max_context_parts,
    settings.retrieval_min_score,
)
app = FastAPI(title="GPC Parts RAG", version="1.0.0")


def error(request_id: str, code: str, message: str, retryable: bool, fallback: str, status: int):
    body = ErrorResponse(
        request_id=request_id,
        error=ErrorBody(code=code, message=message, retryable=retryable, fallback=fallback),
    )
    return JSONResponse(status_code=status, content=body.model_dump())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "catalog_version": catalog.version}


@app.post("/v1/answers")
async def ask(payload: AskRequest):
    try:
        return await service.ask(
            payload.query, payload.request_id, settings.request_timeout_seconds
        )
    except CatalogStaleError as exc:
        return error(
            payload.request_id, "CATALOG_STALE", str(exc), False, "CONVENTIONAL_SEARCH", 503
        )
    except NoEvidenceError as exc:
        return error(payload.request_id, "NO_EVIDENCE", str(exc), False, "CONVENTIONAL_SEARCH", 422)
    except GroundingError as exc:
        return error(
            payload.request_id, "GROUNDING_FAILED", str(exc), False, "CONVENTIONAL_SEARCH", 502
        )
    except DependencyFailedError as exc:
        return error(payload.request_id, "DEPENDENCY_FAILED", str(exc), True, "RETRY", 502)
    except TimeoutError:
        return error(
            payload.request_id, "DEADLINE_EXCEEDED", "generation timed out", True, "RETRY", 504
        )


@app.post("/v1/answers:stream")
async def stream(payload: AskRequest, request: Request):
    async def events() -> AsyncIterator[str]:
        yield f"event: start\ndata: {json.dumps({'request_id': payload.request_id, 'schema_version': '1'})}\n\n"
        task = asyncio.create_task(
            service.ask(payload.query, payload.request_id, settings.request_timeout_seconds)
        )
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                return
            await asyncio.sleep(0.05)
        try:
            result = await task
            yield f"event: content_delta\ndata: {json.dumps({'sequence': 1, 'text': result.answer})}\n\n"
            for citation in result.citations:
                yield f"event: citation\ndata: {citation.model_dump_json()}\n\n"
            yield 'event: completed\ndata: {"finish_reason":"complete"}\n\n'
        except TimeoutError:
            yield 'event: failed\ndata: {"code":"DEADLINE_EXCEEDED","message":"generation timed out","fallback":"RETRY"}\n\n'
        except CatalogStaleError as exc:
            yield f"event: failed\ndata: {json.dumps({'code': 'CATALOG_STALE', 'message': str(exc), 'fallback': 'CONVENTIONAL_SEARCH'})}\n\n"
        except NoEvidenceError as exc:
            yield f"event: failed\ndata: {json.dumps({'code': 'NO_EVIDENCE', 'message': str(exc), 'fallback': 'CONVENTIONAL_SEARCH'})}\n\n"
        except GroundingError as exc:
            yield f"event: failed\ndata: {json.dumps({'code': 'GROUNDING_FAILED', 'message': str(exc), 'fallback': 'CONVENTIONAL_SEARCH'})}\n\n"
        except DependencyFailedError as exc:
            yield f"event: failed\ndata: {json.dumps({'code': 'DEPENDENCY_FAILED', 'message': str(exc), 'fallback': 'RETRY'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")

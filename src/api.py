"""FastAPI backend for pH Companion.

Provides:
- POST /api/chat — SSE stream of one turn: plan, sources, answer
- GET /api/personas — persona gallery
- GET /api/personas/{persona_id} — full persona profile
- GET /api/readings — preset strip readings
- GET /paper/{study_id}?hl=... — reader page with one passage highlighted
- GET /api/health — health check
- GET / — serves static frontend
"""

import json
import logging
import pathlib
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from src.config import load_config

# ---------------------------------------------------------------------------
# App & config
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

app = FastAPI(title="pH Companion")


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Disable caching for static assets during development."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# Load config on module import so env vars are set for litellm
_config = load_config()

# In-memory session store: session_id -> list[dict]
_sessions: Dict[str, List[Dict[str, str]]] = {}

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "en"
    persona_id: Optional[str] = None
    reading: Optional[Dict[str, Any]] = None
    turn_kind: Optional[str] = "question"


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse_event(event: str, data: Any = None) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data) if data is not None else "{}"
    return f"event: {event}\ndata: {payload}\n\n"


# ---------------------------------------------------------------------------
# pH Companion: personas, readings and the gather-then-write stream
# ---------------------------------------------------------------------------


@app.get("/api/personas")
async def get_personas():
    """Return the persona gallery for the UI selector."""
    from src.data.personas import list_personas
    return list_personas()


@app.get("/api/personas/{persona_id}")
async def get_persona(persona_id: str):
    """Return a full persona profile by ID."""
    from src.data.personas import load_persona
    profile = load_persona(persona_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return profile.to_dict()


@app.get("/paper/{study_id}", response_class=HTMLResponse)
async def paper_reader(study_id: str, hl: str = ""):
    """Reader page: the text held for a paper, opened at the cited passage."""
    from src.knowledge_pipeline.fulltext import load_fulltext
    from src.knowledge_pipeline.study_schemas import load_records
    from src.reader import render_paper

    record = load_records().get(study_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return HTMLResponse(render_paper(record, load_fulltext(study_id), hl))


@app.get("/check", response_class=HTMLResponse)
async def link_check():
    """Page for checking the PubMed Central sentence links by hand."""
    from src.knowledge_pipeline.study_schemas import load_records
    from src.reader import render_check_page
    from src.sources.deeplinks import sample_links

    records = sorted(load_records().values(), key=lambda r: (r.year, r.authors))
    papers = [(r, sample_links(r)) for r in records if r.pmcid]
    return HTMLResponse(render_check_page([(r, links) for r, links in papers if links]))


@app.get("/api/readings")
async def get_readings():
    """Return the preset strip readings."""
    from src.data.personas import list_readings
    return list_readings()


_CITATION_NUMBER = re.compile(r"\[\d+\]")


def _ph_initial_state(request: "ChatRequest", history: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build the graph state for one pH Companion turn."""
    from src.agents.writer import NEW_READING_INPUT
    from src.data.personas import load_persona
    from src.data.profile import TestReading, build_profile_summary

    profile = load_persona(request.persona_id or "")
    if profile is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    try:
        reading = TestReading.model_validate(request.reading) if request.reading else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid reading: {exc}") from exc

    turn_kind = "new_reading" if request.turn_kind == "new_reading" and reading else "question"
    user_input = NEW_READING_INPUT if turn_kind == "new_reading" else request.message

    return {
        "messages": list(history),
        "user_input": user_input,
        "route": [],
        "route_reasoning": "",
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
        "patient": profile.to_dict(),
        "patient_summary": build_profile_summary(profile, reading),
        "citations": [],
        "language": request.language or "en",
        "reading": reading.to_dict() if reading else {},
        "turn_kind": turn_kind,
        "queries": [],
        "sources": {},
        "retrieval_trace": [],
        "evidence_gap": {},
        "safety_reasons": [],
    }


async def _ph_event_stream(initial_state: Dict[str, Any], session_id: str, history: List[Dict[str, str]]):
    """Stream one pH Companion turn: the plan, sources as they finish, then the answer."""
    from src.orchestrator.graph import PH_SOURCE_NODES, build_ph_graph, planned_sources

    t_start = time.perf_counter()
    try:
        graph = build_ph_graph()
        yield _sse_event("routing", {"status": "processing"})

        expected: Set[str] = set()
        done: Set[str] = set()
        safety_reasons: List[str] = []
        safety_escalation = False
        writer_update: Dict[str, Any] = {}

        async for event in graph.astream(initial_state, stream_mode="updates"):
            for node_name, update in event.items():
                if not isinstance(update, dict):
                    continue
                if node_name == "planner":
                    sources = planned_sources(update.get("route", []))
                    expected = set(sources)
                    yield _sse_event("routing", {
                        "agents": sources,
                        "queries": update.get("queries", []),
                        "reasoning": update.get("route_reasoning", ""),
                    })
                    for source in sources:
                        yield _sse_event("specialist", {"agent": source, "status": "processing"})
                    if not sources:
                        yield _sse_event("synthesizing", {})
                elif node_name in PH_SOURCE_NODES:
                    safety_reasons += update.get("safety_reasons") or []
                    safety_escalation = safety_escalation or bool(update.get("safety_escalation"))
                    trace = (update.get("retrieval_trace") or [{}])[0]
                    yield _sse_event("specialist", {
                        "agent": node_name,
                        "status": "done",
                        "detail": trace,
                    })
                    done.add(node_name)
                    if done >= expected:
                        yield _sse_event("synthesizing", {})
                elif node_name == "writer":
                    writer_update = update

        final_response = writer_update.get("final_response", "")
        if final_response:
            yield _sse_event("response", {
                "content": final_response,
                "citations": writer_update.get("citations", []),
                "safety_escalation": safety_escalation or writer_update.get("safety_escalation", False),
                "safety_reasons": safety_reasons,
                "session_id": session_id,
            })
            # Citation numbers are per answer; keep them out of the history so
            # the writer does not copy stale numbers into later turns.
            _sessions[session_id] = history + [
                {"role": "user", "content": initial_state["user_input"]},
                {"role": "assistant", "content": _CITATION_NUMBER.sub("", final_response)},
            ]

        logger.info(
            "pH turn completed: session=%s kind=%s citations=%d elapsed=%.3fs",
            session_id, initial_state["turn_kind"],
            len(writer_update.get("citations", [])), time.perf_counter() - t_start,
        )
        yield _sse_event("done", {"session_id": session_id})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing pH turn (session=%s)", session_id)
        yield _sse_event("error", {"message": str(exc)})
        yield _sse_event("done", {"session_id": session_id})


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Accept a user message and stream back agent pipeline events via SSE."""

    session_id = request.session_id or str(uuid.uuid4())
    message = request.message

    # Retrieve or create session history
    if session_id not in _sessions:
        _sessions[session_id] = []
    history = _sessions[session_id]

    if request.persona_id:
        initial_ph_state = _ph_initial_state(request, history)
        return StreamingResponse(
            _ph_event_stream(initial_ph_state, session_id, history),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    raise HTTPException(status_code=422, detail="persona_id is required")


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

_static_dir = pathlib.Path(__file__).parent / "static"

# Mount static assets (CSS, JS) at /static
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main frontend page."""
    index_path = _static_dir / "index.html"
    return HTMLResponse(content=index_path.read_text(), status_code=200)

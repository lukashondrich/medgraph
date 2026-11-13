"""FastAPI backend for the medgraph multiagent healthcare system.

Provides:
- POST /api/chat — SSE stream of agent pipeline events
- GET /api/patients — patient gallery listing
- GET /api/patients/{patient_id} — full patient profile
- GET /api/personas — pH Companion persona gallery
- GET /api/personas/{persona_id} — full persona profile
- GET /api/readings — preset strip readings
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
from src.ollama_health import ollama_health

# ---------------------------------------------------------------------------
# App & config
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

app = FastAPI(title="medgraph — Patient-Aware Health Navigator")


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
    patient_id: Optional[str] = None
    language: Optional[str] = "en"
    # pH Companion: a persona selects the gather-then-write flow.
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
# GET /api/patients
# ---------------------------------------------------------------------------


@app.get("/api/patients")
async def get_patients():
    """Return the patient gallery for the UI selector."""
    from src.data.gallery import list_patients
    return list_patients()


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}
# ---------------------------------------------------------------------------


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    """Return a full patient profile by ID."""
    from src.data.gallery import load_patient
    profile = load_patient(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return profile.to_dict()


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
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
        "patient": profile.to_dict(),
        "patient_summary": build_profile_summary(profile, reading),
        "evidence_context": {},
        "drug_interactions": [],
        "citations": [],
        "router_model_source": "",
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
    """Stream one pH Companion turn: sources as they finish, then the answer."""
    from src.orchestrator.graph import PH_SOURCE_NODES, build_ph_graph

    t_start = time.perf_counter()
    try:
        graph = build_ph_graph()
        # The route is fixed, so the source list is known before anything runs.
        yield _sse_event("routing", {"agents": PH_SOURCE_NODES, "reasoning": "", "fixed": True})
        for source in PH_SOURCE_NODES:
            yield _sse_event("specialist", {"agent": source, "status": "processing"})

        done: Set[str] = set()
        writer_update: Dict[str, Any] = {}
        async for event in graph.astream(initial_state, stream_mode="updates"):
            for node_name, update in event.items():
                if not isinstance(update, dict):
                    continue
                if node_name in PH_SOURCE_NODES:
                    trace = (update.get("retrieval_trace") or [{}])[0]
                    yield _sse_event("specialist", {
                        "agent": node_name,
                        "status": "done",
                        "detail": trace,
                    })
                    done.add(node_name)
                    if done >= set(PH_SOURCE_NODES):
                        yield _sse_event("synthesizing", {})
                elif node_name == "writer":
                    writer_update = update

        final_response = writer_update.get("final_response", "")
        if final_response:
            yield _sse_event("response", {
                "content": final_response,
                "citations": writer_update.get("citations", []),
                "safety_escalation": writer_update.get("safety_escalation", False),
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

    # pH Companion flow: gather evidence first, then write
    if request.persona_id:
        initial_ph_state = _ph_initial_state(request, history)
        return StreamingResponse(
            _ph_event_stream(initial_ph_state, session_id, history),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Load patient context if requested
    patient_dict: Dict[str, Any] = {}
    patient_summary = ""
    if request.patient_id:
        from src.data.gallery import load_patient
        from src.data.patient_context import build_patient_summary
        profile = load_patient(request.patient_id)
        if profile:
            patient_dict = profile.to_dict()
            patient_summary = build_patient_summary(profile)

    # Build language-aware message list
    lang_messages: List[Dict[str, str]] = []
    if request.language and request.language != "en":
        lang_instruction = {
            "de": "WICHTIG: Antworte auf Deutsch. Alle deine Antworten müssen auf Deutsch sein.",
        }
        instruction = lang_instruction.get(
            request.language,
            f"IMPORTANT: Respond in the language code '{request.language}'.",
        )
        lang_messages.append({"role": "system", "content": instruction})

    # Build initial state
    initial_state: Dict[str, Any] = {
        "messages": lang_messages + history + [{"role": "user", "content": message}],
        "user_input": message,
        "route": [],
        "route_reasoning": "",
        "specialist_outputs": {},
        "final_response": "",
        "handoff_chain": [],
        "safety_escalation": False,
        "patient": patient_dict,
        "patient_summary": patient_summary,
        "evidence_context": {},
        "drug_interactions": [],
        "citations": [],
        "router_model_source": "",
        "language": request.language or "en",
    }

    async def event_generator():
        """Stream SSE events as the LangGraph graph executes."""

        from src.orchestrator import build_graph

        graph = build_graph()
        t_start = time.perf_counter()

        try:
            routing_sent = False
            specialists_seen: Set[str] = set()
            synthesizing_sent = False
            final_state: Dict[str, Any] = dict(initial_state)

            # All agent node names that should emit specialist events
            specialist_nodes = {
                "symptom_agent", "medication_agent", "lifestyle_agent",
                "evidence_agent", "drug_check_agent",
            }

            # Signal that routing has started
            yield _sse_event("routing", {"status": "processing"})

            async for event in graph.astream(initial_state, stream_mode="updates"):
                for node_name, state_update in event.items():
                    if state_update is None:
                        continue

                    # Merge updates into our tracking copy
                    if isinstance(state_update, dict):
                        for key, value in state_update.items():
                            if key in ("messages", "handoff_chain", "citations") and isinstance(value, list):
                                if key not in final_state:
                                    final_state[key] = []
                                final_state[key] = final_state[key] + value
                            elif key in ("specialist_outputs", "evidence_context") and isinstance(value, dict):
                                if key not in final_state:
                                    final_state[key] = {}
                                final_state[key] = {**final_state[key], **value}
                            else:
                                final_state[key] = value

                    # Router node completed
                    if node_name == "router" and not routing_sent:
                        route = final_state.get("route", [])
                        reasoning = final_state.get("route_reasoning", "")
                        model_source = final_state.get("router_model_source", "cloud")
                        yield _sse_event("routing", {
                            "agents": route,
                            "reasoning": reasoning,
                            "model_source": model_source,
                        })
                        routing_sent = True
                        for agent in route:
                            yield _sse_event("specialist", {
                                "agent": agent,
                                "status": "processing",
                            })

                    # Specialist node completed
                    elif node_name in specialist_nodes:
                        agent_label = node_name.replace("_agent", "")
                        specialist_outputs = final_state.get("specialist_outputs", {})
                        output = specialist_outputs.get(agent_label, "")
                        if agent_label not in specialists_seen:
                            specialists_seen.add(agent_label)
                            event_data: Dict[str, Any] = {
                                "agent": agent_label,
                                "status": "done",
                                "output": output,
                            }
                            # Include extra data for new agents
                            if agent_label == "evidence":
                                event_data["citations"] = final_state.get("citations", [])
                            elif agent_label == "drug_check":
                                event_data["drug_interactions"] = final_state.get("drug_interactions", [])
                            yield _sse_event("specialist", event_data)

                            # Emit synthesizing status once all routed specialists are done
                            routed = set(final_state.get("route", []))
                            if not synthesizing_sent and routed and specialists_seen >= routed:
                                yield _sse_event("synthesizing", {})
                                synthesizing_sent = True

                    # Synthesizer node completed
                    elif node_name == "synthesizer":
                        final_response = final_state.get("final_response", "")
                        safety = final_state.get("safety_escalation", False)
                        if final_response:
                            yield _sse_event("response", {
                                "content": final_response,
                                "safety_escalation": safety,
                                "session_id": session_id,
                            })

            # Update session history
            _sessions[session_id] = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": final_state.get("final_response", "")},
            ]

            elapsed = time.perf_counter() - t_start
            route = final_state.get("route", [])
            safety = final_state.get("safety_escalation", False)
            logger.info(
                "Request completed: session=%s agents=%s safety=%s elapsed=%.3fs",
                session_id, route, safety, elapsed,
            )
            yield _sse_event("done", {"session_id": session_id})

        except Exception as exc:
            logger.exception("Error processing chat request (session=%s)", session_id)
            yield _sse_event("error", {"message": str(exc)})
            yield _sse_event("done", {"session_id": session_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /api/ollama-status
# ---------------------------------------------------------------------------


@app.get("/api/ollama-status")
async def ollama_status():
    """Return Ollama availability for the frontend model indicator."""
    import os
    available = await ollama_health.check()
    model = os.environ.get("OLLAMA_ROUTER_MODEL") if available else None
    return {"available": available, "model": model}


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

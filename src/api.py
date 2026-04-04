"""FastAPI backend for the medgraph multiagent healthcare system.

Provides:
- POST /api/chat — SSE stream of agent pipeline events
- GET /api/patients — patient gallery listing
- GET /api/patients/{patient_id} — full patient profile
- GET /api/health — health check
- GET / — serves static frontend
"""

import json
import logging
import pathlib
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

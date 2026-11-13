# Orchestrator Architecture

`graph.py` builds one graph, `build_ph_graph()`:

```
START -> planner -> [safety_rules + chosen sources, in parallel] -> writer -> END
```

- `planned_sources(route)` turns the planner's route into node names in display order and always adds `safety_rules`. An empty or unusable route gives no sources.
- `route_to_sources(state)` returns one `Send` per source, or a single `Send("writer")` when nothing is to be looked up (off-topic).
- Every source node has an edge to `writer`; LangGraph runs the writer once, after all sources of the turn have finished.
- All node instances can be injected (`build_ph_graph(planner=..., study_library=...)`), which the tests use to replace the search with a fake library.

The graph is stateless: conversation history is passed in by the API.

"""Body text of a paper from its stored PDF.

For papers without official full text. The PDF is read with PDF.js in a
headless Chrome, the same engine the viewer uses, so a passage taken from
this text is found again when the viewer looks for it.

A PDF holds positioned fragments, not paragraphs. This module rebuilds
lines, drops running headers and footers, finds section headings, joins
lines into paragraphs and stops at the reference list. The result is
rougher than official full text; ``python -m src.knowledge_pipeline.corpus
pdftext --compare`` measures it against a paper where both exist.

Needs Google Chrome. Only local files are loaded (plus PDF.js from its CDN).
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import re
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Optional

from .fulltext import FullText, Section, classify_section

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/"

_DUMP_PAGE = """<!DOCTYPE html><meta charset="utf-8"><script src="%spdf.min.js"></script><script>
pdfjsLib.GlobalWorkerOptions.workerSrc = "%spdf.worker.min.js";
(async () => {
  try {
    const pdf = await pdfjsLib.getDocument({url: "paper.pdf"}).promise;
    const pages = [];
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n);
      const view = page.getViewport({scale: 1});
      const content = await page.getTextContent();
      pages.push({width: view.width, height: view.height, items: content.items.map(i => ({
        s: i.str, x: i.transform[4], y: i.transform[5], h: i.height || Math.abs(i.transform[3]), w: i.width, eol: !!i.hasEOL,
        f: (content.styles[i.fontName] || {}).fontFamily || "", n: i.fontName}))});
    }
    window.dump = JSON.stringify(pages);
  } catch (e) { window.dump = JSON.stringify({error: String(e)}); }
})();
</script>""" % (PDFJS, PDFJS)

_HEADING_WORDS = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(abstract|introduction|background|methods?|materials? and methods|"
    r"patients and methods|subjects and methods|study design|statistical analys[ie]s|results?|findings|"
    r"discussion|comments?|conclusions?|results and discussion|limitations|references?(?: list)?|bibliography|"
    r"acknowledge?ments?|funding|conflicts? of interest|author contributions?|supplementary .*|"
    r"supporting information|competing interests?|literature cited)\s*:?$",
    re.I,
)
_STOP_HEADING = re.compile(r"^(?:\d+\.?\s+)?(references?(?: list)?|bibliography|literature cited)\s*:?$", re.I)
# An entry of a reference list: "(17) Yudin MH. ..." or "... BJOG 2002; 109(1):34-43."
_REFERENCE_ENTRY = re.compile(
    r"^\(?\[?\d{1,3}[.)\]]\s+[A-Z][A-Za-z'-]+ [A-Z]{1,4}[,. ]|\b(?:19|20)\d{2}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*\w?\d+"
)
_CAPTION_START = re.compile(r"^(fig(?:ure)?\.?|table|supplementary (?:fig|table))\s*S?\d+", re.I)
_SKIP_HEADING = re.compile(r"acknowledg|funding|conflict|competing|author contribution|supplement|supporting", re.I)
_CAPTION = re.compile(r"^(fig(?:ure)?\.?|table|supplementary|doi:|https?://|©|copyright|correspond|received|accepted|keywords?)\b", re.I)


# ── Reading the PDF ───────────────────────────────────────────────────────


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D102 - keep the build output clean
        pass


def dump_pdf(pdf_path: Path, port: int = 9351) -> list[dict]:
    """Text fragments of every page, with position and size."""
    return asyncio.run(_dump(pdf_path, port))


async def _dump(pdf_path: Path, port: int) -> list[dict]:
    import aiohttp

    with tempfile.TemporaryDirectory(prefix="pdftext-") as workdir:
        work = Path(workdir)
        (work / "dump.html").write_text(_DUMP_PAGE)
        (work / "paper.pdf").write_bytes(pdf_path.read_bytes())
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(_QuietHandler, directory=workdir)
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        chrome = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={work / 'profile'}", "--no-first-run", "--disable-gpu", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            tabs = []
            for _ in range(60):
                try:
                    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                    break
                except Exception:  # noqa: BLE001 - Chrome is still starting
                    time.sleep(0.2)
            page = [t for t in tabs if t["type"] == "page"][0]
            async with aiohttp.ClientSession() as session, session.ws_connect(
                page["webSocketDebuggerUrl"], max_msg_size=0
            ) as ws:
                counter = 0

                async def cmd(method: str, **params) -> dict:
                    nonlocal counter
                    counter += 1
                    mine = counter
                    await ws.send_json({"id": mine, "method": method, "params": params})
                    while True:
                        message = json.loads((await ws.receive()).data)
                        if message.get("id") == mine:
                            return message.get("result", {})

                await cmd("Page.enable")
                await cmd("Page.navigate", url=f"http://127.0.0.1:{server.server_address[1]}/dump.html")
                deadline = time.time() + 120
                while time.time() < deadline:
                    result = await cmd("Runtime.evaluate", expression="window.dump || ''", returnByValue=True)
                    value = result.get("result", {}).get("value")
                    if value:
                        data = json.loads(value)
                        if isinstance(data, dict):
                            raise RuntimeError(f"PDF could not be read: {data.get('error')}")
                        return data
                    await asyncio.sleep(0.3)
                raise TimeoutError("PDF took too long to read")
        finally:
            chrome.terminate()
            server.shutdown()


# ── Rebuilding the text ───────────────────────────────────────────────────


class Line:
    def __init__(self, page: int, items: list[dict]) -> None:
        self.page = page
        self.text = re.sub(r"\s+", " ", "".join(i["s"] for i in items)).strip()
        self.x = min(i["x"] for i in items)
        self.right = max(i["x"] + i["w"] for i in items)
        self.y = items[0]["y"]
        sizes = [round(i["h"], 1) for i in items if i["s"].strip()]
        self.size = statistics.mode(sizes) if sizes else 0.0
        fonts = [i["n"] for i in items if i["s"].strip()]
        self.font = statistics.mode(fonts) if fonts else ""


def to_lines(pages: list[dict]) -> list[Line]:
    """Group fragments into lines, in the order the PDF stores them."""
    lines: list[Line] = []
    for number, page in enumerate(pages, 1):
        current: list[dict] = []
        for item in page["items"]:
            if current and abs(item["y"] - current[-1]["y"]) > max(2.0, 0.5 * (current[-1]["h"] or 8)):
                lines.append(Line(number, current))
                current = []
            current.append(item)
            if item["eol"]:
                lines.append(Line(number, current))
                current = []
        if current:
            lines.append(Line(number, current))
    return [line for line in lines if line.text]


def drop_page_furniture(lines: list[Line], pages: list[dict]) -> list[Line]:
    """Remove running headers, footers and page numbers.

    A line counts as furniture when it sits in the top or bottom margin, or
    when the same text (digits aside) turns up on at least three pages.
    """
    def key(line: Line) -> str:
        return re.sub(r"\d+", "#", line.text.lower())

    repeated = {k for k, n in Counter(key(l) for l in lines).items() if n >= 3 and len(k) < 120}
    kept = []
    for line in lines:
        height = pages[line.page - 1]["height"]
        in_margin = line.y > height * 0.94 or line.y < height * 0.05
        # A section heading can be the first line of a page; it is not a running header.
        margin_note = in_margin and len(line.text) < 100 and not _HEADING_WORDS.match(line.text)
        if key(line) in repeated or margin_note or re.fullmatch(r"[\d\s|/.-]+", line.text):
            continue
        kept.append(line)
    return kept


def is_heading(line: Line, body_size: float, body_font: str) -> bool:
    words = line.text.split()
    numbered = bool(re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z]", line.text))  # "3.2. Recurrent vaginal infections and ..."
    if not words or len(words) > (16 if numbered else 9) or line.text.endswith((".", ",", ";")):
        return False
    if _HEADING_WORDS.match(line.text):
        return True
    # A short line set larger or in another face than the body text, starting with a capital.
    stands_out = line.size > body_size * 1.08 or (line.font != body_font and line.size >= body_size * 0.98)
    unnumbered = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", line.text)  # "2.1. Causes of vaginitis"
    plain_words = not re.search(r"[\d,;=<>%@]", unnumbered)  # author lines and table cells have these
    return (
        stands_out and plain_words and (numbered or line.text[0].isupper()) and len(line.text) > 3
        and (numbered or len(words) <= 7) and not _CAPTION.match(line.text)
    )


def looks_like_prose(text: str) -> bool:
    """False for table rows, reference entries and other non-sentences."""
    solid = text.replace(" ", "")
    if not solid or sum(c.isalpha() for c in solid) / len(solid) < 0.72:
        return False
    words = text.split()
    if len(words) < 8 or not re.search(r"[.!?][\"')\]]?$", text.strip()):
        return False
    return sum(1 for w in words if w[0].islower()) / len(words) > 0.45


class Block:
    """One item of a paper's outline: a candidate heading or a paragraph."""

    def __init__(self, kind: str, text: str) -> None:
        self.kind = kind  # "heading" or "text"
        self.text = text


def build_blocks(lines: list[Line]) -> list[Block]:
    """Turn lines into an ordered outline of candidate headings and paragraphs.

    Figure legends, table rows and other non-prose are left out here. Which
    headings are real, and where each section starts, is decided afterwards
    (by rules in ``heuristic_segments`` or by a model in ``llm_segments``).
    """
    body = [l for l in lines if len(l.text) > 25]
    if not body:
        return []
    # Many journals set methods and references smaller than the main text, and
    # those can outnumber it. The main text is the largest size that still
    # makes up a real share of the lines.
    shares = Counter(l.size for l in body)
    body_size = max(size for size, count in shares.items() if count >= 0.10 * len(body))
    body_font = statistics.mode(l.font for l in body if l.size == body_size)
    typical_width = statistics.median(l.right - l.x for l in body if l.size == body_size)

    blocks: list[Block] = []
    paragraph: list[str] = []
    previous: Optional[Line] = None
    in_caption = False

    def flush() -> None:
        nonlocal paragraph
        text = " ".join(paragraph)
        text = re.sub(r"(\w)- (?=[a-z])", r"\1", text)  # undo hyphenation at line ends
        paragraph = []
        if looks_like_prose(text) and not _CAPTION.match(text):
            blocks.append(Block("text", text))

    for line in lines:
        gap = previous is None or line.page != previous.page or abs(previous.y - line.y) > body_size * 2.2
        if _CAPTION_START.match(line.text):
            # A figure legend or table title: skip it up to the next gap in the text.
            flush()
            in_caption = True
            previous = line
            continue
        if in_caption:
            if not gap and not is_heading(line, body_size, body_font):
                previous = line
                continue
            in_caption = False
            previous = None
        if is_heading(line, body_size, body_font):
            flush()
            blocks.append(Block("heading", line.text))
            previous = None
            continue
        if abs(line.size - body_size) > body_size * 0.12:
            continue  # footnotes, superscripts on their own line, figure lettering
        if previous is not None:
            new_block = line.page != previous.page or abs(previous.y - line.y) > body_size * 2.2 or line.y > previous.y + 1
            short_before = (previous.right - previous.x) < typical_width * 0.82
            indented = line.x - previous.x > body_size * 0.6
            ended = previous.text.endswith((".", "?", "!", ")", "]"))
            if ended and (indented or short_before or (new_block and abs(previous.y - line.y) > body_size * 2.2)):
                flush()
        paragraph.append(line.text)
        previous = line
    flush()
    return blocks


# Section kinds. "front", "abstract", "references" and "skip" are never stored.
SEGMENT_KINDS = {
    "front", "abstract", "introduction", "methods", "results", "discussion",
    "conclusion", "review", "references", "skip",
}
_DROPPED_KINDS = {"front", "abstract", "references", "skip"}


def _clean_title(text: str) -> str:
    return re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text).rstrip(":").strip()


def heuristic_segments(blocks: list[Block]) -> tuple[list[dict], set[int]]:
    """Decide the sections by rule: known heading words, and inheritance below them."""
    segments = [{"start": 0, "kind": "front", "title": "Front matter"}]
    seen_findings = False
    for index, block in enumerate(blocks):
        if block.kind == "text":
            # A reference list without a heading we recognise.
            if (seen_findings or index > 0.4 * len(blocks)) and _REFERENCE_ENTRY.search(block.text):
                segments.append({"start": index, "kind": "references", "title": "References"})
                break
            continue
        title = _clean_title(block.text)
        if _STOP_HEADING.match(block.text):
            # "Reference" can also head a citation box on the first page.
            if seen_findings or index > 0.4 * len(blocks):
                segments.append({"start": index, "kind": "references", "title": title})
                break
            continue
        kind = "skip" if _SKIP_HEADING.search(title) else classify_section(title)
        if kind == "other":
            previous = segments[-1]["kind"]
            if previous in ("front", "skip"):
                continue  # still front matter, or a stray line
            kind = previous  # a subheading inside Results stays Results
        seen_findings = seen_findings or kind in ("results", "discussion", "conclusion")
        if kind != segments[-1]["kind"]:
            segments.append({"start": index, "kind": kind, "title": title})
    return segments, set()


def sections_from_blocks(blocks: list[Block], segments: list[dict], not_headings: set[int]) -> list[Section]:
    """Apply section boundaries to the outline.

    Inside a segment every real heading starts a new titled section of the
    segment's kind, so subsection titles are kept.
    """
    starts = {seg["start"]: seg for seg in segments}
    sections: list[Section] = []
    kind = "front"
    for index, block in enumerate(blocks):
        if index in starts:
            kind = starts[index]["kind"]
            if kind == "references":
                break
            if kind not in _DROPPED_KINDS:
                sections.append(Section(title=_clean_title(starts[index]["title"]) or kind.title(), kind=kind))
        if kind in _DROPPED_KINDS:
            continue
        if block.kind == "heading":
            if index in not_headings:
                continue
            if index not in starts:
                sections.append(Section(title=_clean_title(block.text), kind=kind))
            continue
        if not sections:
            sections.append(Section(title=kind.title(), kind=kind))
        sections[-1].paragraphs.append(block.text)
    return [s for s in sections if s.paragraphs]


def build_sections(lines: list[Line]) -> list[Section]:
    """Sections decided by rule (no model call)."""
    blocks = build_blocks(lines)
    return sections_from_blocks(blocks, *heuristic_segments(blocks))


# ── Section detection by a model ──────────────────────────────────────────

_SEGMENT_PROMPT = """You are given the outline of a scientific paper as it was extracted from its PDF, in reading order.
H items are lines that look like headings. P items are paragraphs (only their first words are shown).

Paper: {title}
Type: {design}

Decide where each part of the paper starts. Return one JSON object:
{{
  "segments": [{{"start": <item number>, "kind": "<kind>", "title": "<short section title>"}}, ...],
  "not_headings": [<numbers of H items that are not headings>]
}}

Kinds
- front: title, authors, affiliations, journal and copyright lines, keywords
- abstract: the abstract or summary, including its own "Methods", "Results", "Conclusion" parts
- introduction: introduction or background
- methods: how the study was done, including statistics
- results: what this study found ("Results", "Findings", "Results and discussion", and their subsections)
- discussion: interpretation of this study's findings, strengths and limitations
- conclusion: conclusions of this study
- review: the main body of a review article or guideline, under topical headings
- references: the reference list
- skip: acknowledgements, funding, conflicts of interest, author contributions, supplementary material, appendices

Rules
- The first segment starts at item 0. Give segments in order. A segment runs until the next one starts.
- Start a new segment only where the kind changes. A subheading inside Results does not start a new segment.
- A segment may start at a P item when a part begins without a heading (for example the reference list, or the
  body text right after the abstract).
- The abstract's own "Results" or "Conclusion" lines belong to the abstract, not to results.
- For a review or guideline, use "review" for the body, not "results" or "discussion".
- not_headings: H items that are author names, affiliations, journal names, table or figure labels, or other
  lines that are not section headings.

Outline
{outline}
"""


def _outline(blocks: list[Block]) -> str:
    rows = []
    for index, block in enumerate(blocks):
        if block.kind == "heading":
            rows.append(f"{index} H: {block.text[:120]}")
        else:
            words = block.text.split()
            rows.append(f"{index} P: {' '.join(words[:14])} … ({len(words)} words)")
    return "\n".join(rows)


def validate_segments(data: dict, n_blocks: int) -> tuple[list[dict], set[int]]:
    """Check a model's answer; raises ValueError when it cannot be used."""
    segments = []
    last = -1
    for seg in data.get("segments") or []:
        start, kind = seg.get("start"), seg.get("kind")
        if not isinstance(start, int) or not 0 <= start < n_blocks or start <= last:
            raise ValueError(f"bad segment start {start!r}")
        if kind not in SEGMENT_KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        segments.append({"start": start, "kind": kind, "title": str(seg.get("title") or kind.title())})
        last = start
    if not segments or segments[0]["start"] != 0:
        raise ValueError("segments must start at item 0")
    not_headings = {i for i in data.get("not_headings") or [] if isinstance(i, int)}
    return segments, not_headings


async def llm_segments(blocks: list[Block], title: str, design: str, model: str) -> tuple[list[dict], set[int]]:
    """Ask a model where the sections start. The text itself is never changed by it."""
    import litellm

    prompt = _SEGMENT_PROMPT.format(title=title, design=design, outline=_outline(blocks))
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                ),
                timeout=120,
            )
            return validate_segments(json.loads(response.choices[0].message.content), len(blocks))
        except Exception as exc:  # noqa: BLE001 - timeout, provider, JSON or validation error
            last_error = exc
    raise RuntimeError(f"section detection failed: {last_error!r}")


def extract_fulltext(
    study_id: str,
    pdf_path: Path,
    *,
    title: str = "",
    design: str = "",
    model: Optional[str] = None,
) -> FullText:
    """Read a PDF and return its body text as sections of paragraphs.

    With ``model`` the section boundaries are decided by that model, falling
    back to the rules when its answer cannot be used. Without it, rules only.
    """
    pages = dump_pdf(pdf_path)
    blocks = build_blocks(drop_page_furniture(to_lines(pages), pages))
    segments, not_headings = heuristic_segments(blocks)
    if model and blocks:
        try:
            segments, not_headings = asyncio.run(llm_segments(blocks, title, design, model))
        except RuntimeError as exc:
            print(f"   {study_id}: {exc}; using rule-based sections")
    return FullText(
        study_id=study_id, pmcid="", source="pdf",
        sections=sections_from_blocks(blocks, segments, not_headings),
    )

"""Links that open a paper at the cited sentence.

Two targets:

- **PubMed Central.** A "scroll to text" link carries the first and last
  words of the passage:
  ``https://pmc.ncbi.nlm.nih.gov/articles/PMC123/#:~:text=<start>,<end>``.
  The reader's browser scrolls to that text and highlights it. This only
  works when the words match the page exactly and the link is followed by a
  real click, so anchors are chosen conservatively from the text we hold for
  the paper (the official full text when it is open access, otherwise the
  abstract).
- **The reader page of this app** (``/paper/<study id>``), which shows the
  text we hold and highlights the passage itself. It works for every paper
  and is the fallback when no safe PubMed Central link can be built.

PubMed Central pages must not be loaded by automated tools (the site
answers with a browser check), so these links cannot be verified against the
live page in bulk. They are checked by hand; see docs/eval-results.md.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Optional

from src.knowledge_pipeline.fulltext import FullText, load_fulltext
from src.knowledge_pipeline.study_schemas import StudyRecord

PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
MIN_START_WORDS = 4
MIN_END_WORDS = 2
MAX_ANCHOR_WORDS = 14

# "Methods: We sampled ..." — the heading of a structured abstract is a
# separate element on the article page, so it must not be part of an anchor.
_LABEL = re.compile(r"^[A-Z][A-Za-z &/]{2,40}: (?=[A-Z0-9])")
_INNER_LABEL = re.compile(r"(?<=[.!?]) [A-Z][A-Za-z &/]{2,40}: (?=[A-Z0-9])")
_WORD_EDGE = re.compile(r"^\W+|\W+$")


def normalize(text: str) -> str:
    return re.sub(r"[ \t\r\n]+", " ", text).strip()


def document_text(record: StudyRecord, fulltext: Optional[FullText]) -> str:
    """All running text we hold for a paper, in page order."""
    parts = [record.title, record.abstract]
    if fulltext is not None:
        for section in fulltext.sections:
            parts.extend(section.paragraphs)
    return normalize(" \n ".join(parts))


def _trim(words: list[str], from_start: bool) -> list[str]:
    """Drop edge words without letters or digits, and edge punctuation."""
    words = list(words)
    while words:
        index = 0 if from_start else -1
        cleaned = _WORD_EDGE.sub("", words[index]) if not from_start else re.sub(r"^\W+", "", words[index])
        if not from_start:
            cleaned = re.sub(r"\W+$", "", words[index])
        if cleaned and re.search(r"\w", cleaned) and cleaned[0 if from_start else -1].isalnum():
            words[index] = cleaned
            return words
        words.pop(index)
    return words


def make_anchors(passage: str, document: str) -> Optional[tuple[str, str]]:
    """Choose start and end words that pin ``passage`` down in ``document``.

    The browser takes the first place where the start words occur, then the
    first place after it where the end words occur. So the start has to be
    unique, the end must not occur earlier inside the passage, and both must
    begin and end on a letter or digit (a browser matches whole words; an
    anchor that starts with "±" or "(" is not found).

    Returns None when no safe pair exists.
    """
    passage = normalize(passage)
    position = document.find(passage)
    if position < 0:
        return None

    # Anchors are taken from the first and last sentence parts that are free
    # of abstract headings.
    head = _LABEL.sub("", passage)
    first_part = _INNER_LABEL.split(head)[0]
    last_part = _INNER_LABEL.split(head)[-1]

    start_words = _trim(first_part.split(" "), from_start=True)
    end_words = _trim(last_part.split(" "), from_start=False)
    if len(start_words) < MIN_START_WORDS or len(end_words) < MIN_END_WORDS:
        return None

    # Plain-ASCII anchors are preferred: symbols such as "±" are the likeliest
    # place for the page and our copy of the text to differ.
    starts = []
    for n in range(MIN_START_WORDS, min(MAX_ANCHOR_WORDS, len(start_words)) + 1):
        candidate = " ".join(_trim(start_words[:n], from_start=False))
        if document.count(candidate) == 1:
            starts.append(candidate)
    if not starts:
        return None
    start = next((c for c in starts if c.isascii()), starts[0])
    start_at = document.find(start)
    if not position <= start_at < position + len(passage):
        return None

    true_end = position + len(passage)
    ends = []
    for n in range(MIN_END_WORDS, min(MAX_ANCHOR_WORDS, len(end_words)) + 1):
        candidate = " ".join(_trim(end_words[-n:], from_start=True))
        found = document.find(candidate, start_at + len(start))
        # The first match after the start must be the passage's own ending
        # (allowing for trailing punctuation that was trimmed off).
        if found >= 0 and true_end - 3 <= found + len(candidate) <= true_end:
            ends.append(candidate)
    if not ends:
        return None
    return start, next((c for c in ends if c.isascii()), ends[0])


def _encode(text: str) -> str:
    # "-", "," and "&" are part of the link syntax and must be escaped too.
    return urllib.parse.quote(text, safe="").replace("-", "%2D")


def pmc_url(record: StudyRecord, passage: str, fulltext: Optional[FullText] = None) -> Optional[str]:
    """Link to the passage on PubMed Central, or None when it cannot be built safely."""
    if not record.pmcid:
        return None
    anchors = make_anchors(passage, document_text(record, fulltext))
    if anchors is None:
        return None
    start, end = anchors
    return PMC_ARTICLE_URL.format(pmcid=record.pmcid) + "#:~:text=" + _encode(start) + "," + _encode(end)


def reader_url(record: StudyRecord, passage: str) -> str:
    """Link to the passage in this app's reader page."""
    return f"/paper/{record.study_id}?hl=" + urllib.parse.quote(normalize(passage), safe="")


def quote_links(record: StudyRecord, passage: str, section: str = "Abstract") -> dict:
    """Everything the interface needs to show one quote and open it in place."""
    fulltext = load_fulltext(record.study_id)
    return {
        "text": passage,
        "section": section,
        "pmc_url": pmc_url(record, passage, fulltext),
        "reader_url": reader_url(record, passage),
    }


def sample_links(record: StudyRecord, per_paper: int = 3) -> list[dict]:
    """A few passages per paper, spread from the top of the article to the end.

    Used by the link check page: an abstract passage near the top, then
    passages from the middle and the end of the full text when it is held.
    """
    from src.knowledge_pipeline.study_schemas import all_passages

    fulltext = load_fulltext(record.study_id)
    linked = []
    for passage in all_passages(record):
        url = pmc_url(record, passage.text, fulltext)
        if url:
            linked.append({
                "passage_id": passage.passage_id,
                "text": passage.text,
                "section": passage.section,
                "pmc_url": url,
                "reader_url": reader_url(record, passage.text),
            })
    if len(linked) <= per_paper:
        return linked
    step = (len(linked) - 1) / (per_paper - 1)
    return [linked[round(i * step)] for i in range(per_paper)]

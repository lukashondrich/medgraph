"""Reader page: shows the text held for a paper and highlights one passage.

This is the app's own way to open a paper at the cited sentence. It works
for every paper in the library, including those that are not on PubMed
Central, and shows as much text as the library holds: the full text for
open-access papers, otherwise the abstract.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from src.knowledge_pipeline.fulltext import FullText
from src.knowledge_pipeline.study_schemas import StudyRecord
from src.sources.deeplinks import PMC_ARTICLE_URL, normalize

_LABEL_SPLIT = re.compile(r"(?<=[.!?]) (?=[A-Z][A-Za-z &/]{2,40}: [A-Z0-9])")


def _mark(paragraph: str, highlight: str) -> tuple[str, bool]:
    """Escape a paragraph and wrap the highlighted passage, if it is in it."""
    position = paragraph.find(highlight) if highlight else -1
    if position < 0:
        return html.escape(paragraph), False
    end = position + len(highlight)
    return (
        html.escape(paragraph[:position])
        + '<mark id="cited">' + html.escape(paragraph[position:end]) + "</mark>"
        + html.escape(paragraph[end:])
    ), True


def render_paper(record: StudyRecord, fulltext: Optional[FullText], highlight: str = "") -> str:
    """Build the reader page for one paper."""
    highlight = normalize(highlight)
    found = False
    blocks: list[str] = []

    def add_section(title: str, paragraphs: list[str]) -> None:
        nonlocal found
        blocks.append(f"<h2>{html.escape(title)}</h2>")
        for paragraph in paragraphs:
            marked, hit = _mark(normalize(paragraph), "" if found else highlight)
            found = found or hit
            blocks.append(f"<p>{marked}</p>")

    # A passage may run across two labelled parts of the abstract, so the
    # abstract is searched as one text first and only then split for display.
    abstract = normalize(record.abstract)
    if highlight and highlight in abstract:
        marked, found = _mark(abstract, highlight)
        blocks.append(f"<h2>Abstract</h2><p>{marked}</p>")
    else:
        add_section("Abstract", _LABEL_SPLIT.split(abstract))
    if fulltext is not None:
        for section in fulltext.sections:
            add_section(section.title, section.paragraphs)

    size = f"{record.sample_size:,} participants" if record.sample_size else "size not stated"
    if record.pmcid:
        original = PMC_ARTICLE_URL.format(pmcid=record.pmcid)
        original_label = "Open the article on PubMed Central"
    else:
        original, original_label = record.url, "Open the record on PubMed"
    holding = (
        "the full text of this open-access paper" if fulltext is not None
        else "the abstract of this paper; the full article is at the publisher"
    )
    notice = "" if found or not highlight else (
        '<p class="reader-note reader-note--warn" role="status">The cited passage could not be located in this text.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(record.authors)} {record.year} — pH Companion reader</title>
  <link rel="stylesheet" href="/static/style.css" />
  <script>
    document.documentElement.setAttribute("data-theme",
      localStorage.getItem("medgraph-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
    if (localStorage.getItem("medgraph-contrast") === "high") {{
      document.documentElement.setAttribute("data-contrast", "high");
    }}
  </script>
</head>
<body class="reader">
  <main class="reader-page">
    <p class="reader-brand">pH <span class="header-accent">Companion</span> <span class="header-tag">Reader</span></p>
    <h1>{html.escape(record.title)}</h1>
    <p class="reader-byline">{html.escape(record.authors)}, {record.year}{" · " + html.escape(record.journal) if record.journal else ""}</p>
    <p class="reader-meta">{html.escape(record.design_label)} · {size}</p>
    <p class="reader-note">This page shows {holding}, as held in the pH Companion library.
      <a href="{html.escape(original)}" target="_blank" rel="noopener noreferrer">{original_label} <span aria-hidden="true">&#8599;</span></a></p>
    {notice}
    <article class="reader-text">
      {"".join(blocks)}
    </article>
  </main>
  <script>
    var cited = document.getElementById("cited");
    if (cited) {{
      cited.scrollIntoView({{ block: "center" }});
      cited.setAttribute("tabindex", "-1");
      cited.focus({{ preventScroll: true }});
    }}
  </script>
</body>
</html>"""


def render_check_page(papers: list[tuple[StudyRecord, list[dict]]]) -> str:
    """A page for checking by hand that the PubMed Central links land on the cited sentence."""
    total = sum(len(links) for _, links in papers)
    rows = []
    for record, links in papers:
        kind = "full text" if any(l["section"] != "Abstract" for l in links) else "abstract only"
        rows.append(
            f'<section class="check-paper"><h2>{html.escape(record.authors)} {record.year} '
            f'<span class="check-kind">{html.escape(record.pmcid or "")} · {kind}</span></h2>'
            f'<p class="check-title">{html.escape(record.title)}</p>'
        )
        for link in links:
            key = html.escape(link["passage_id"])
            rows.append(
                f'<div class="check-row" data-key="{key}">'
                f'<p class="check-section">{html.escape(link["section"])}</p>'
                f'<blockquote class="cite-quote">{html.escape(link["text"])}</blockquote>'
                '<div class="check-actions">'
                f'<a class="cite-open cite-open--primary" href="{html.escape(link["pmc_url"])}" target="_blank" rel="noopener noreferrer">Open on PubMed Central &#8599;</a>'
                f'<a class="cite-open" href="{html.escape(link["reader_url"])}" target="_blank" rel="noopener noreferrer">Reader &#8599;</a>'
                '<span class="check-verdict" role="group" aria-label="Result">'
                '<button type="button" data-verdict="ok">Highlighted</button>'
                '<button type="button" data-verdict="top">Opened at top</button>'
                '<button type="button" data-verdict="wrong">Wrong place</button>'
                "</span></div></div>"
            )
        rows.append("</section>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Link check — pH Companion</title>
  <link rel="stylesheet" href="/static/style.css" />
  <script>
    document.documentElement.setAttribute("data-theme",
      localStorage.getItem("medgraph-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  </script>
</head>
<body class="reader">
  <main class="reader-page">
    <p class="reader-brand">pH <span class="header-accent">Companion</span> <span class="header-tag">Link check</span></p>
    <h1>Do the links open the paper at the cited sentence?</h1>
    <p class="reader-note">{total} links across {len(papers)} papers on PubMed Central. Click
      <strong>Open on PubMed Central</strong>: the article should open in a new tab, scroll to the quoted text
      and highlight it. Then mark what happened. Results are kept in this browser.
      If PubMed Central shows a "checking your browser" page, wait for it to pass and click the link again.</p>
    <p class="check-summary" id="summary" role="status"></p>
    <p><button type="button" class="cite-open" id="copy">Copy results</button>
       <button type="button" class="cite-open" id="reset">Clear results</button></p>
    {"".join(rows)}
  </main>
  <script>
    var KEY = "ph-link-check";
    var results = {{}};
    try {{ results = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
    var LABELS = {{ ok: "highlighted", top: "opened at top", wrong: "wrong place" }};

    function render() {{
      var counts = {{ ok: 0, top: 0, wrong: 0 }};
      document.querySelectorAll(".check-row").forEach(function (row) {{
        var verdict = results[row.dataset.key];
        row.dataset.result = verdict || "";
        row.querySelectorAll("button").forEach(function (b) {{
          b.setAttribute("aria-pressed", b.dataset.verdict === verdict ? "true" : "false");
        }});
        if (verdict) counts[verdict] += 1;
      }});
      var done = counts.ok + counts.top + counts.wrong;
      document.getElementById("summary").textContent =
        done + " of {total} checked: " + counts.ok + " highlighted, " + counts.top +
        " opened at top, " + counts.wrong + " wrong place.";
    }}

    document.addEventListener("click", function (e) {{
      var button = e.target.closest("[data-verdict]");
      if (button) {{
        var key = button.closest(".check-row").dataset.key;
        if (results[key] === button.dataset.verdict) delete results[key];
        else results[key] = button.dataset.verdict;
        localStorage.setItem(KEY, JSON.stringify(results));
        render();
      }}
    }});
    document.getElementById("reset").addEventListener("click", function () {{
      results = {{}}; localStorage.removeItem(KEY); render();
    }});
    document.getElementById("copy").addEventListener("click", function () {{
      var lines = [navigator.userAgent, document.getElementById("summary").textContent];
      Object.keys(results).sort().forEach(function (k) {{ lines.push(k + ": " + LABELS[results[k]]); }});
      navigator.clipboard.writeText(lines.join("\\n")).then(function () {{
        document.getElementById("copy").textContent = "Copied";
      }});
    }});
    render();
  </script>
</body>
</html>"""

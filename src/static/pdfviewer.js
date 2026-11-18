/* ==========================================================
   pH Companion - PDF viewer
   Shows a stored PDF with PDF.js and highlights one passage on
   the original pages.

   A PDF holds text as positioned fragments: words are split at
   line ends, hyphenated, and interrupted by page furniture. So
   the passage is matched on letters and digits only, and the
   match is mapped back to the fragments it came from.
   ========================================================== */

(function () {
  "use strict";

  var PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS + "pdf.worker.min.js";

  var root = document.getElementById("pdfPages");
  var status = document.getElementById("pdfStatus");
  var spans = [];      // every text fragment, in reading order
  var hay = "";        // letters and digits of the whole document
  var hayMap = [];     // for each character of `hay`: [span index, offset in that span]
  var EDGE = 40;       // characters used at each end for the tolerant match

  /** Letters and digits only, lower case; ligatures such as "ﬁ" are spelled out. */
  function reduce(text, onChar) {
    for (var i = 0; i < text.length; i++) {
      var plain = text[i].normalize("NFKD").toLowerCase();
      for (var k = 0; k < plain.length; k++) {
        if (/[\p{L}\p{N}]/u.test(plain[k])) onChar(plain[k], i);
      }
    }
  }

  function reduced(text) {
    var out = "";
    reduce(text, function (c) { out += c; });
    return out;
  }

  async function renderPage(pdf, number, width) {
    var page = await pdf.getPage(number);
    var base = page.getViewport({ scale: 1 });
    var scale = width / base.width;
    var viewport = page.getViewport({ scale: scale });
    var ratio = window.devicePixelRatio || 1;

    var holder = document.createElement("div");
    holder.className = "pdf-page";
    holder.style.width = viewport.width + "px";
    holder.style.height = viewport.height + "px";
    holder.setAttribute("data-page", number);

    var canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = viewport.width + "px";
    canvas.style.height = viewport.height + "px";
    holder.appendChild(canvas);

    var layer = document.createElement("div");
    layer.className = "textLayer";
    layer.style.setProperty("--scale-factor", scale);
    holder.appendChild(layer);
    root.appendChild(holder);

    await page.render({
      canvasContext: canvas.getContext("2d"),
      viewport: viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
    }).promise;

    var content = await page.getTextContent();
    await pdfjsLib.renderTextLayer({ textContentSource: content, container: layer, viewport: viewport }).promise;

    layer.querySelectorAll("span").forEach(function (span) {
      if (!span.firstChild || span.children.length) return;
      var index = spans.length;
      spans.push(span);
      reduce(span.textContent, function (c, offset) {
        hay += c;
        hayMap.push([index, offset]);
      });
    });
  }

  /** Where the passage sits in `hay`: [start, end, how], or null. */
  function locate(passage) {
    var needle = reduced(passage);
    if (needle.length < 12) return null;
    var at = hay.indexOf(needle);
    if (at >= 0) return [at, at + needle.length - 1, "exact"];

    // Tolerant match: the start and the end of the passage, close enough
    // together. Covers a page number, footnote mark or header that landed
    // inside the passage.
    if (needle.length < EDGE * 2) return null;
    var head = needle.slice(0, EDGE);
    var tail = needle.slice(-EDGE);
    var from = hay.indexOf(head);
    while (from >= 0) {
      var to = hay.indexOf(tail, from + EDGE);
      if (to >= 0 && to + EDGE - from <= needle.length * 1.6) {
        return [from, to + EDGE - 1, "edges"];
      }
      from = hay.indexOf(head, from + 1);
    }
    return null;
  }

  function clearMarks() {
    root.querySelectorAll("span[data-marked]").forEach(function (span) {
      span.textContent = span.textContent;
      span.removeAttribute("data-marked");
    });
  }

  function escapeHTML(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function mark(start, end) {
    var ranges = {};
    for (var i = start; i <= end; i++) {
      var entry = hayMap[i];
      var r = ranges[entry[0]] || (ranges[entry[0]] = [entry[1], entry[1]]);
      r[0] = Math.min(r[0], entry[1]);
      r[1] = Math.max(r[1], entry[1]);
    }
    var first = hayMap[start][0];
    var last = hayMap[end][0];
    var firstMark = null;
    for (var s = first; s <= last; s++) {
      var span = spans[s];
      var text = span.textContent;
      // Fragments between the first and the last are covered whole, spaces included.
      var a = s === first ? ranges[s][0] : 0;
      var b = s === last ? ranges[s][1] : text.length - 1;
      span.innerHTML =
        escapeHTML(text.slice(0, a)) + "<mark>" + escapeHTML(text.slice(a, b + 1)) + "</mark>" + escapeHTML(text.slice(b + 1));
      span.setAttribute("data-marked", "1");
      firstMark = firstMark || span.querySelector("mark");
    }
    return firstMark;
  }

  /** Highlight a passage. Returns {found, how, page}. */
  function findPassage(passage, scroll) {
    clearMarks();
    var where = locate(passage);
    if (!where) return { found: false };
    var firstMark = mark(where[0], where[1]);
    if (scroll && firstMark) firstMark.scrollIntoView({ block: "center" });
    var page = spans[hayMap[where[0]][0]].closest(".pdf-page");
    return { found: true, how: where[2], page: Number(page.getAttribute("data-page")) };
  }
  window.findPassage = findPassage;

  async function start() {
    var config = window.PDF_VIEWER;
    try {
      var pdf = await pdfjsLib.getDocument({ url: config.file }).promise;
      var width = Math.min(root.clientWidth, 900);
      for (var n = 1; n <= pdf.numPages; n++) {
        status.textContent = "Loading page " + n + " of " + pdf.numPages + "…";
        await renderPage(pdf, n, width);
      }
      window.pdfInfo = { pages: pdf.numPages, characters: hay.length };
      if (config.highlight) {
        var result = findPassage(config.highlight, true);
        status.textContent = result.found
          ? "The cited passage is highlighted on page " + result.page + "."
          : "The cited passage could not be located in this PDF.";
        status.className = result.found ? "reader-note" : "reader-note reader-note--warn";
      } else {
        status.textContent = "";
        status.hidden = true;
      }
    } catch (err) {
      status.textContent = "This PDF could not be displayed.";
      status.className = "reader-note reader-note--warn";
      console.error(err);
    }
    window.pdfReady = true;
  }

  start();
})();

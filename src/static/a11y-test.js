/* ==========================================================
   medgraph — Accessibility Validation (axe-core)

   Load this script in development to run automated WCAG 2.2
   AA checks. Add ?a11y to the URL to activate.

   Usage:
     http://localhost:8000/?a11y

   Results appear in the browser console and as an on-page
   overlay summarizing violations.
   ========================================================== */

(function () {
  "use strict";

  // Only run if ?a11y is in the URL
  if (!window.location.search.includes("a11y")) return;

  var AXE_CDN =
    "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js";

  function loadAxe() {
    return new Promise(function (resolve, reject) {
      if (window.axe) {
        resolve(window.axe);
        return;
      }
      var script = document.createElement("script");
      script.src = AXE_CDN;
      script.onload = function () {
        resolve(window.axe);
      };
      script.onerror = function () {
        reject(new Error("Failed to load axe-core from CDN"));
      };
      document.head.appendChild(script);
    });
  }

  function createOverlay(results) {
    var violations = results.violations;
    var passes = results.passes.length;
    var incomplete = results.incomplete.length;

    var overlay = document.createElement("div");
    overlay.id = "a11y-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-label", "Accessibility test results");
    overlay.style.cssText =
      "position:fixed;top:0;right:0;width:420px;max-height:100vh;" +
      "overflow-y:auto;background:#1a1a2e;color:#e8e8f0;font-family:monospace;" +
      "font-size:13px;padding:16px;z-index:99999;box-shadow:-4px 0 20px rgba(0,0,0,0.3);" +
      "border-left:3px solid " +
      (violations.length > 0 ? "#ef5350" : "#66bb6a") +
      ";";

    var html = "<h2 style='margin:0 0 12px;font-size:16px;'>" +
      "WCAG 2.2 AA Audit" +
      "</h2>";

    html +=
      "<div style='margin-bottom:12px;padding:8px;border-radius:6px;background:" +
      (violations.length > 0 ? "#4a1010" : "#103010") +
      ";'>" +
      "<strong>" + violations.length + "</strong> violations &middot; " +
      "<strong>" + passes + "</strong> passes &middot; " +
      "<strong>" + incomplete + "</strong> needs review" +
      "</div>";

    if (violations.length === 0) {
      html +=
        "<p style='color:#66bb6a;font-weight:bold;'>All automated checks passed.</p>";
    }

    violations.forEach(function (v, i) {
      var impact = v.impact || "unknown";
      var impactColor = {
        critical: "#ef5350",
        serious: "#ff9800",
        moderate: "#ffeb3b",
        minor: "#90caf9",
      };
      html +=
        "<details style='margin-bottom:8px;'>" +
        "<summary style='cursor:pointer;padding:6px;background:#2a2a3e;border-radius:4px;'>" +
        "<span style='color:" +
        (impactColor[impact] || "#ccc") +
        ";font-weight:bold;'>[" +
        impact.toUpperCase() +
        "]</span> " +
        escapeHTML(v.id) +
        " <span style='opacity:0.7;'>(" +
        v.nodes.length +
        " nodes)</span>" +
        "</summary>" +
        "<div style='padding:8px 0 4px 12px;'>" +
        "<p style='margin:0 0 4px;'>" +
        escapeHTML(v.description) +
        "</p>" +
        "<p style='margin:0 0 4px;opacity:0.7;font-size:11px;'>" +
        escapeHTML(v.helpUrl) +
        "</p>" +
        v.nodes
          .map(function (n) {
            return (
              "<code style='display:block;padding:4px;background:#111;border-radius:3px;" +
              "margin:4px 0;font-size:11px;word-break:break-all;'>" +
              escapeHTML(n.html.substring(0, 200)) +
              "</code>"
            );
          })
          .join("") +
        "</div></details>";
    });

    html +=
      "<button id='a11y-close' style='margin-top:12px;padding:8px 16px;" +
      "background:#4f6ef7;color:#fff;border:none;border-radius:6px;cursor:pointer;" +
      "font-family:monospace;font-size:13px;'>Close</button>";

    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    document.getElementById("a11y-close").addEventListener("click", function () {
      overlay.remove();
    });
  }

  function escapeHTML(str) {
    var div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  // Run after page loads
  window.addEventListener("load", function () {
    // Wait a moment for dynamic content to render
    setTimeout(function () {
      loadAxe()
        .then(function (axe) {
          return axe.run(document, {
            runOnly: {
              type: "tag",
              values: ["wcag2a", "wcag2aa", "wcag22aa", "best-practice"],
            },
          });
        })
        .then(function (results) {
          console.group("axe-core WCAG 2.2 AA results");
          console.log("Violations:", results.violations.length);
          console.log("Passes:", results.passes.length);
          console.log("Incomplete:", results.incomplete.length);
          if (results.violations.length > 0) {
            console.table(
              results.violations.map(function (v) {
                return {
                  id: v.id,
                  impact: v.impact,
                  description: v.description,
                  nodes: v.nodes.length,
                };
              })
            );
          }
          console.groupEnd();
          createOverlay(results);
        })
        .catch(function (err) {
          console.error("axe-core audit failed:", err);
        });
    }, 1500);
  });
})();

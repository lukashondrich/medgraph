/* ==========================================================
   pH Companion - Frontend Client
   WCAG 2.2 AA · DE/EN · Speech input · Dark/High-contrast
   ========================================================== */

(function () {
  "use strict";

  // --- i18n shorthand ---
  var t = MedGraphI18n.t;
  var phrase = MedGraphI18n.phrase;

  // --- State ---
  var sessionId = newSessionId();
  var isProcessing = false;
  var personas = [];
  var readings = [];
  var selectedPersona = null; // gallery card
  var selectedProfile = null; // full profile
  var selectedReading = null;
  var isListening = false;
  var recognition = null;
  var lookupCounter = 0;
  var citeTrigger = null;

  var GROUP_ORDER = ["safety", "matched", "reference_range", "guideline", "overall"];
  var GROUP_KEYS = {
    safety: "groupSafety",
    matched: "groupMatched",
    reference_range: "groupRange",
    guideline: "groupGuideline",
    overall: "groupOverall",
  };
  var SOURCE_KEYS = {
    plan: "srcPlan",
    safety_rules: "srcSafetyRules",
    guidelines: "srcGuidelines",
    reference_ranges: "srcReferenceRanges",
    study_library: "srcStudyLibrary",
    writer: "srcWriter",
  };
  var LOW_CONFIDENCE = 0.7;
  var SCALE_MIN = 3.5;
  var SCALE_MAX = 7.5;
  // Shortest time a lookup step shows as "in progress" before its check mark.
  var STEP_MS = 550;

  // --- DOM refs ---
  var chatContainer = document.getElementById("chatContainer");
  var chatForm = document.getElementById("chatForm");
  var messageInput = document.getElementById("messageInput");
  var sendBtn = document.getElementById("sendBtn");
  var personaGallery = document.getElementById("personaGallery");
  var profileCard = document.getElementById("profileCard");
  var profileName = document.getElementById("profileName");
  var profileHeadline = document.getElementById("profileHeadline");
  var profileDetails = document.getElementById("profileDetails");
  var resultCard = document.getElementById("resultCard");
  var readingGallery = document.getElementById("readingGallery");
  var phScale = document.getElementById("phScale");
  var phMarker = document.getElementById("phMarker");
  var phMeta = document.getElementById("phMeta");
  var langToggle = document.getElementById("langToggle");
  var themeToggle = document.getElementById("themeToggle");
  var contrastToggle = document.getElementById("contrastToggle");
  var micBtn = document.getElementById("micBtn");
  var srAnnouncements = document.getElementById("srAnnouncements");
  var personaInfoBtn = document.getElementById("personaInfoBtn");
  var personaInfoTooltip = document.getElementById("personaInfoTooltip");
  var citeSheet = document.getElementById("citeSheet");
  var citeBackdrop = document.getElementById("citeBackdrop");
  var citeClose = document.getElementById("citeClose");
  var citeGroup = document.getElementById("citeGroup");
  var citeTitle = document.getElementById("citeTitle");
  var citeContent = document.getElementById("citeContent");

  // --- Init ---
  initTheme();
  initContrast();
  initSpeechRecognition();
  MedGraphI18n.applyTranslations();

  chatForm.addEventListener("submit", handleSubmit);
  langToggle.addEventListener("click", toggleLanguage);
  themeToggle.addEventListener("click", toggleTheme);
  contrastToggle.addEventListener("click", toggleContrast);
  micBtn.addEventListener("click", toggleMic);
  personaInfoBtn.addEventListener("click", function () {
    personaInfoTooltip.classList.toggle("visible");
  });
  document.addEventListener("click", function (e) {
    if (!personaInfoBtn.contains(e.target) && !personaInfoTooltip.contains(e.target)) {
      personaInfoTooltip.classList.remove("visible");
    }
  });
  chatContainer.addEventListener("click", handleChatClick);
  citeClose.addEventListener("click", closeCitation);
  citeBackdrop.addEventListener("click", closeCitation);
  document.addEventListener("keydown", handleSheetKeys);

  loadGalleries();

  // ============================================================
  // Theme
  // ============================================================

  function initTheme() {
    var saved = localStorage.getItem("medgraph-theme");
    if (!saved) {
      saved = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    applyTheme(saved);
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeToggle.setAttribute(
      "aria-label",
      theme === "dark" ? t("lightMode") : t("darkMode")
    );
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-theme");
    var next = current === "dark" ? "light" : "dark";
    localStorage.setItem("medgraph-theme", next);
    applyTheme(next);
  }

  // ============================================================
  // High contrast
  // ============================================================

  function initContrast() {
    var saved = localStorage.getItem("medgraph-contrast");
    if (saved === "high") {
      document.documentElement.setAttribute("data-contrast", "high");
      contrastToggle.setAttribute("aria-pressed", "true");
    } else {
      contrastToggle.setAttribute("aria-pressed", "false");
    }
  }

  function toggleContrast() {
    var current = document.documentElement.getAttribute("data-contrast");
    if (current === "high") {
      document.documentElement.removeAttribute("data-contrast");
      localStorage.setItem("medgraph-contrast", "normal");
      contrastToggle.setAttribute("aria-pressed", "false");
    } else {
      document.documentElement.setAttribute("data-contrast", "high");
      localStorage.setItem("medgraph-contrast", "high");
      contrastToggle.setAttribute("aria-pressed", "true");
    }
  }

  // ============================================================
  // Language
  // ============================================================

  function toggleLanguage() {
    var next = MedGraphI18n.getLang() === "en" ? "de" : "en";
    MedGraphI18n.setLanguage(next);

    if (recognition) {
      recognition.lang = next === "de" ? "de-DE" : "en-US";
    }
    applyTheme(document.documentElement.getAttribute("data-theme"));

    // Re-render the parts built in JS; the conversation keeps its language.
    renderPersonaGallery();
    renderProfileCard();
    renderReadingGallery();
    renderScale();
  }

  // ============================================================
  // Speech Recognition (Web Speech API)
  // ============================================================

  function initSpeechRecognition() {
    var SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      micBtn.disabled = true;
      micBtn.setAttribute("aria-label", t("micUnsupported"));
      micBtn.title = t("micUnsupported");
      return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = MedGraphI18n.getLang() === "de" ? "de-DE" : "en-US";

    recognition.onresult = function (event) {
      var transcript = event.results[0][0].transcript;
      messageInput.value = transcript;
      messageInput.focus();
      announce(transcript);
    };
    recognition.onerror = function () {
      setListeningState(false);
    };
    recognition.onend = function () {
      setListeningState(false);
    };
  }

  function toggleMic() {
    if (!recognition) {
      announce(t("micUnsupported"));
      return;
    }
    if (isListening) {
      recognition.stop();
      setListeningState(false);
    } else {
      try {
        recognition.start();
        setListeningState(true);
      } catch (e) {
        setListeningState(false);
      }
    }
  }

  function setListeningState(listening) {
    isListening = listening;
    micBtn.classList.toggle("listening", listening);
    micBtn.setAttribute("aria-label", listening ? t("micStop") : t("micStart"));
    if (listening) {
      announce(t("listening"));
    }
  }

  // ============================================================
  // Screen reader announcements
  // ============================================================

  function announce(text) {
    srAnnouncements.textContent = "";
    requestAnimationFrame(function () {
      srAnnouncements.textContent = text;
    });
  }

  // ============================================================
  // Personas and readings
  // ============================================================

  async function loadGalleries() {
    try {
      var responses = await Promise.all([
        fetch("/api/personas"),
        fetch("/api/readings"),
      ]);
      personas = await responses[0].json();
      readings = await responses[1].json();
      renderPersonaGallery();
      renderReadingGallery();
    } catch (err) {
      console.error("Failed to load profiles:", err);
      personaGallery.innerHTML =
        '<span class="gallery-error" role="alert">' +
        escapeHTML(t("galleryError")) +
        "</span>";
    }
  }

  function renderPersonaGallery() {
    personaGallery.innerHTML = "";
    personas.forEach(function (p) {
      var btn = document.createElement("button");
      var selected = selectedPersona && selectedPersona.persona_id === p.persona_id;
      btn.className = "patient-btn";
      btn.type = "button";
      btn.setAttribute("data-id", p.persona_id);
      btn.setAttribute("aria-pressed", selected ? "true" : "false");
      btn.disabled = isProcessing;
      btn.innerHTML =
        "<strong>" + escapeHTML(p.name) + "</strong> " +
        '<span class="patient-btn-meta">' + escapeHTML(String(p.age)) + "</span>";
      btn.addEventListener("click", function () {
        selectPersona(p);
      });
      personaGallery.appendChild(btn);
    });
  }

  async function selectPersona(p) {
    if (isProcessing) return;
    if (selectedPersona && selectedPersona.persona_id === p.persona_id) return;

    try {
      var resp = await fetch("/api/personas/" + encodeURIComponent(p.persona_id));
      if (!resp.ok) throw new Error("Server responded with " + resp.status);
      selectedProfile = await resp.json();
    } catch (err) {
      console.error("Failed to load profile:", err);
      announce(t("galleryError"));
      return;
    }
    selectedPersona = p;

    renderPersonaGallery();
    renderProfileCard();
    profileCard.open = true; // show who was picked and what is known about her
    resultCard.hidden = false;
    setInputEnabled(true);
    announce(p.name + ": " + t("personaSelected"));

    // A different woman gets a fresh conversation. If a reading is already
    // chosen, the same value is explained again for her.
    resetConversation();
    if (selectedReading) {
      runTurn("new_reading", "");
    }
  }

  function profileSummaryLine(profile) {
    var parts = [
      String(profile.age),
      ancestryLabel(profile.ancestry),
      t(profile.menopausal_status),
    ];
    if (profile.pregnancy !== "not_pregnant") parts.push(t(profile.pregnancy));
    return parts.join(" · ");
  }

  function renderProfileCard() {
    if (!selectedProfile) {
      profileCard.hidden = true;
      return;
    }
    var p = selectedProfile;
    profileCard.hidden = false;
    profileName.textContent = p.name;
    profileHeadline.textContent = profileSummaryLine(p);

    var cycle = null;
    if (p.cycle_regular !== null && p.cycle_regular !== undefined) {
      cycle = p.cycle_regular ? t("valRegular") : t("valIrregular");
      if (p.cycle_day) cycle += ", " + t("valDay") + " " + p.cycle_day;
    }
    var rows = [
      [t("profAge"), String(p.age)],
      [t("profAncestry"), ancestryLabel(p.ancestry)],
      [t("profCountry"), phrase(p.country_of_residence)],
      [t("profMenopause"), t(p.menopausal_status)],
      [t("profPregnancy"), t(p.pregnancy)],
      [t("profCycle"), cycle],
      [t("profContraception"), p.hormonal_contraception || t("valNone")],
      [t("profHrt"), p.hrt || t("valNone")],
      [t("profAntibiotics"), p.recent_antibiotics ? t("valYes") : t("valNo")],
      [t("profSymptoms"), (p.symptoms || []).join(", ") || t("valNone")],
      [t("profHistory"), (p.history || []).join(", ") || t("valNone")],
    ];
    profileDetails.innerHTML = rows
      .filter(function (row) {
        return row[1] !== null;
      })
      .map(function (row) {
        return (
          '<div class="profile-row"><dt>' + escapeHTML(row[0]) + "</dt><dd>" +
          escapeHTML(row[1]) + "</dd></div>"
        );
      })
      .join("");
  }

  function ancestryLabel(key) {
    if (selectedPersona && selectedProfile && selectedProfile.ancestry === key) {
      return phrase(selectedPersona.ancestry);
    }
    return key;
  }

  function renderReadingGallery() {
    readingGallery.innerHTML = "";
    readings.forEach(function (r) {
      var btn = document.createElement("button");
      var selected = selectedReading && selectedReading.id === r.id;
      btn.className = "patient-btn reading-btn";
      btn.type = "button";
      btn.setAttribute("data-id", r.id);
      btn.setAttribute("aria-pressed", selected ? "true" : "false");
      btn.disabled = isProcessing;
      var html = "<strong>pH " + escapeHTML(r.ph.toFixed(1)) + "</strong>";
      if (r.confidence < LOW_CONFIDENCE) {
        html += ' <span class="patient-btn-meta">' + escapeHTML(t("readingUnclear")) + "</span>";
      }
      btn.innerHTML = html;
      btn.addEventListener("click", function () {
        selectReading(r);
      });
      readingGallery.appendChild(btn);
    });
  }

  function selectReading(r) {
    if (isProcessing || !selectedPersona) return;
    selectedReading = r;
    renderReadingGallery();
    renderScale();
    announce(t("readingSelected") + ": pH " + r.ph.toFixed(1));

    // A new reading starts a fresh conversation with its interpretation.
    resetConversation();
    runTurn("new_reading", "");
  }

  function renderScale() {
    if (!selectedReading) {
      phScale.hidden = true;
      return;
    }
    var r = selectedReading;
    var fraction = (r.ph - SCALE_MIN) / (SCALE_MAX - SCALE_MIN);
    fraction = Math.max(0, Math.min(1, fraction));
    phScale.hidden = false;
    phMarker.style.left = (fraction * 100).toFixed(1) + "%";
    phMarker.textContent = r.ph.toFixed(1);

    var percent = Math.round(r.confidence * 100);
    var meta =
      t("readConfidence") + " " + percent + "% · " + t("takenAt") + " " + formatTime(r.taken_at);
    if (r.confidence < LOW_CONFIDENCE) {
      phMeta.innerHTML =
        '<span class="ph-scale-warning">' + escapeHTML(t("readingUncertain")) + "</span> · " +
        escapeHTML(meta);
    } else {
      phMeta.textContent = meta;
    }
  }

  function formatTime(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return "";
    return date.toLocaleTimeString(MedGraphI18n.getLang(), {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function resetConversation() {
    sessionId = newSessionId();
    closeCitation();
    Array.prototype.slice.call(chatContainer.children).forEach(function (child) {
      if (!child.classList.contains("welcome-message")) {
        chatContainer.removeChild(child);
      }
    });
    var welcome = chatContainer.querySelector(".welcome-message");
    if (welcome) {
      welcome.removeAttribute("aria-hidden");
      welcome.style.display = "";
    }
  }

  // ============================================================
  // Turns
  // ============================================================

  function handleSubmit(e) {
    e.preventDefault();
    var message = messageInput.value.trim();
    if (!message) return;
    messageInput.value = "";
    runTurn("question", message);
  }

  async function runTurn(kind, message) {
    if (isProcessing || !selectedPersona) return;
    isProcessing = true;
    setInputEnabled(false);

    var welcome = chatContainer.querySelector(".welcome-message");
    if (welcome) {
      welcome.setAttribute("aria-hidden", "true");
      welcome.style.display = "none";
    }

    if (kind === "new_reading") {
      appendUserMessage(t("newReading") + ": pH " + selectedReading.ph.toFixed(1));
    } else {
      appendUserMessage(message);
    }

    var lookupEl = createLookupCard();
    chatContainer.appendChild(lookupEl);
    scrollToBottom();

    var body = {
      message: message,
      session_id: sessionId,
      language: MedGraphI18n.getLang(),
      persona_id: selectedPersona.persona_id,
      turn_kind: kind,
    };
    if (selectedReading) {
      body.reading = {
        ph: selectedReading.ph,
        confidence: selectedReading.confidence,
        taken_at: selectedReading.taken_at,
      };
    }

    try {
      await streamChat(body, lookupEl);
    } catch (err) {
      lookupEl._failed = true;
      var errorEl = appendAssistantMessage(t("errorGeneric"), false, []);
      errorEl.setAttribute("role", "alert");
      finishLookupCard(lookupEl);
      console.error("Chat stream error:", err);
    }
    // The stream can finish before the steps have been shown; wait for them.
    lookupEl._streamEnded = true;
    if (lookupEl._sequence) {
      await lookupEl._sequence;
    }
    if (!lookupEl._finished) {
      finishLookupCard(lookupEl);
    }

    isProcessing = false;
    setInputEnabled(true);
    if (kind === "question") messageInput.focus();
  }

  // ============================================================
  // SSE streaming
  // ============================================================

  async function streamChat(body, lookupEl) {
    var response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error("Server responded with " + response.status);
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";

    while (true) {
      var result = await reader.read();
      if (result.done) break;

      buffer += decoder.decode(result.value, { stream: true });
      var events = parseSSEBuffer(buffer);
      buffer = events.remainder;

      for (var i = 0; i < events.parsed.length; i++) {
        handleSSEEvent(events.parsed[i], lookupEl);
      }
    }
  }

  function parseSSEBuffer(buffer) {
    var parsed = [];
    var blocks = buffer.split("\n\n");
    var remainder = blocks.pop();

    for (var b = 0; b < blocks.length; b++) {
      var block = blocks[b];
      if (!block.trim()) continue;

      var eventType = "message";
      var data = "";
      var lines = block.split("\n");

      for (var l = 0; l < lines.length; l++) {
        var line = lines[l];
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          data = line.slice(6);
        }
      }

      try {
        parsed.push({ type: eventType, data: data ? JSON.parse(data) : {} });
      } catch (e) {
        console.warn("Failed to parse SSE data:", data);
      }
    }

    return { parsed: parsed, remainder: remainder || "" };
  }

  function handleSSEEvent(event, lookupEl) {
    switch (event.type) {
      // Events only record what happened. The lookup card shows it step by
      // step, top to bottom, in runLookupSequence().
      case "routing":
        if (event.data.agents && !lookupEl._sequence) {
          lookupEl._sequence = runLookupSequence(lookupEl, event.data.agents);
        }
        break;

      case "specialist":
        if (event.data.status === "done") {
          lookupEl._results[event.data.agent] = event.data.detail || {};
        }
        break;

      case "response":
        if (event.data.session_id) {
          sessionId = event.data.session_id;
        }
        lookupEl._response = event.data;
        break;

      case "error":
        lookupEl._failed = true;
        var errEl = appendAssistantMessage(t("errorGeneric"), false, []);
        errEl.setAttribute("role", "alert");
        finishLookupCard(lookupEl);
        console.error("Server error:", event.data && event.data.message);
        break;

      case "done":
        if (event.data && event.data.session_id) {
          sessionId = event.data.session_id;
        }
        break;
    }
  }

  // ============================================================
  // Lookup card: what was looked up, as it happens
  // ============================================================

  function createLookupCard() {
    lookupCounter += 1;
    var listId = "lookupSteps" + lookupCounter;
    var el = document.createElement("div");
    el.className = "pipeline-status";
    el._trace = {};
    el._results = {};
    el._started = Date.now();

    el.innerHTML =
      '<div class="pipeline-card">' +
        '<button type="button" class="pipeline-toggle" aria-expanded="true" aria-controls="' + listId + '">' +
          '<span class="pipeline-title">' +
            '<span class="spinner" aria-hidden="true"></span> ' +
            '<span class="pipeline-title-text">' + escapeHTML(t("lookingUp")) + "</span>" +
          "</span>" +
          '<span class="chevron" aria-hidden="true"></span>' +
        "</button>" +
        '<ul class="lookup-steps" id="' + listId + '">' + stepHTML("plan") + "</ul>" +
      "</div>";
    setStepState(el, "plan", "processing");

    var toggle = el.querySelector(".pipeline-toggle");
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      setLookupOpen(el, !open);
    });
    return el;
  }

  function setLookupOpen(el, open) {
    el.querySelector(".pipeline-toggle").setAttribute("aria-expanded", open ? "true" : "false");
    el.querySelector(".lookup-steps").hidden = !open;
  }

  function stepHTML(agent) {
    return (
      '<li class="lookup-step pending" data-agent="' + escapeHTML(agent) + '">' +
        '<span class="step-icon" aria-hidden="true"></span>' +
        '<span class="step-body">' +
          '<span class="step-name">' + escapeHTML(sourceName(agent)) + "</span>" +
          '<span class="step-detail"></span>' +
        "</span>" +
        '<span class="sr-only step-status"></span>' +
      "</li>"
    );
  }

  function addLookupSteps(el, agents) {
    var list = el.querySelector(".lookup-steps");
    list.insertAdjacentHTML("beforeend", agents.concat(["writer"]).map(stepHTML).join(""));
    if (agents.length) {
      announce(t("lookingUp") + ": " + agents.map(sourceName).join(", "));
    }
  }

  function setStepState(el, agent, state) {
    var step = el.querySelector('.lookup-step[data-agent="' + agent + '"]');
    if (!step) return null;
    step.className = "lookup-step " + state;
    var icon = step.querySelector(".step-icon");
    if (state === "processing") {
      icon.innerHTML = '<span class="spinner"></span>';
      step.querySelector(".step-status").textContent = t("stepProcessing");
    } else if (state === "done") {
      icon.innerHTML = "&#10003;";
      step.querySelector(".step-status").textContent = t("stepDone");
    }
    return step;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  /** Resolve once `ready()` is true and at least STEP_MS have passed since `start`. */
  async function stepFinished(el, start, ready) {
    while (!ready() && !el._failed && !el._streamEnded) {
      await sleep(50);
    }
    var remaining = STEP_MS - (Date.now() - start);
    if (remaining > 0 && !el._failed) {
      await sleep(remaining);
    }
  }

  /**
   * Walk through the lookup steps from top to bottom. Each step shows its
   * spinner for at least STEP_MS, even when its result arrived at once, so
   * the work reads as a sequence. The answer appears after the last step.
   */
  async function runLookupSequence(el, agents) {
    await stepFinished(el, el._started, function () {
      return true;
    });
    setStepState(el, "plan", "done");
    addLookupSteps(el, agents);
    scrollToBottom();

    for (var i = 0; i < agents.length && !el._failed; i++) {
      var agent = agents[i];
      setStepState(el, agent, "processing");
      await stepFinished(el, Date.now(), function () {
        return el._results[agent] !== undefined;
      });
      var detail = el._results[agent];
      if (detail === undefined) break;
      var step = setStepState(el, agent, "done");
      el._trace[agent] = detail;
      if (step) {
        step.querySelector(".step-detail").innerHTML = stepDetailHTML(agent, detail);
      }
      scrollToBottom();
    }
    if (el._failed) return;

    setStepState(el, "writer", "processing");
    announce(t("srcWriter"));
    scrollToBottom();
    await stepFinished(el, Date.now(), function () {
      return !!el._response;
    });
    if (el._failed || !el._response) return;

    setStepState(el, "writer", "done");
    await sleep(STEP_MS / 2);
    finishLookupCard(el);
    appendAssistantMessage(
      el._response.content,
      el._response.safety_escalation,
      el._response.citations || [],
      el._response.safety_reasons || []
    );
  }

  function stepDetailHTML(agent, detail) {
    var counts = detail.counts || {};
    if (detail.error) {
      return escapeHTML(t("detailError"));
    }
    if (agent === "reference_ranges") {
      var who = (detail.query || "").split(", ").map(phrase).join(", ");
      return escapeHTML(t("detailRanges", { found: counts.found || 0, query: who }));
    }
    if (agent === "safety_rules") {
      return counts.fired
        ? '<span class="step-flag">' + escapeHTML(t("detailSafetyFired", { n: counts.fired })) + "</span>"
        : escapeHTML(t("detailSafetyNone"));
    }
    if (agent === "guidelines") {
      return escapeHTML(t("detailGuidelines", { found: counts.found || 0 }));
    }
    if (agent === "study_library") {
      var queries = detail.queries || (detail.query ? [detail.query] : []);
      var lines = [];
      if (queries.length) {
        var searched = t("detailSearched") + ": “" + queries[0] + "”";
        if (queries.length > 1) {
          searched += " " + t("detailMore", { n: queries.length - 1 });
        }
        lines.push('<span class="step-line">' + escapeHTML(searched) + "</span>");
      }
      var found = t("detailStudies", { used: counts.used || 0, found: counts.found || 0 });
      var line = escapeHTML(found);
      if (counts.matched) {
        line +=
          ' · <span class="step-matched">' +
          escapeHTML(t("detailMatched", { matched: counts.matched })) +
          "</span>";
      }
      lines.push('<span class="step-line">' + line + "</span>");
      return lines.join("");
    }
    return "";
  }

  function finishLookupCard(el) {
    var title = el.querySelector(".pipeline-title");
    if (!title || el._finished) return;
    el._finished = true;

    var trace = el._trace || {};
    var sources = Object.keys(trace).length;
    var parts = [t("summarySources", { n: sources })];
    var library = (trace.study_library || {}).counts;
    if (library) {
      parts.push(t("summaryStudies", { used: library.used || 0 }));
      if (library.matched) {
        parts.push(t("detailMatched", { matched: library.matched }));
      }
    }
    title.innerHTML =
      '<span class="pipeline-check" aria-hidden="true">&#10003;</span> ' +
      '<span class="pipeline-title-text">' + escapeHTML(parts.join(" · ")) + "</span>";
    el.querySelector(".pipeline-toggle").setAttribute("aria-label", t("lookedUp") + ": " + parts.join(", "));
    setLookupOpen(el, false);
  }

  function sourceName(agent) {
    return SOURCE_KEYS[agent] ? t(SOURCE_KEYS[agent]) : capitalize(agent.replace(/_/g, " "));
  }

  // ============================================================
  // Messages
  // ============================================================

  function appendUserMessage(text) {
    var el = document.createElement("article");
    el.className = "message message-user";
    el.setAttribute("aria-label", t("messageFrom") + " " + t("you"));
    el.innerHTML =
      '<div class="message-label" aria-hidden="true">' + escapeHTML(t("you")) + "</div>" +
      '<div class="message-bubble">' + escapeHTML(text) + "</div>";
    chatContainer.appendChild(el);
    scrollToBottom();
  }

  function appendAssistantMessage(text, safetyEscalation, citations, safetyReasons) {
    var el = document.createElement("article");
    el.className = "message message-assistant";
    el.setAttribute("aria-label", t("responseFrom"));

    var byNumber = {};
    (citations || []).forEach(function (c) {
      byNumber[c.number] = c;
    });
    el._citations = byNumber;

    var html =
      '<div class="message-label" aria-hidden="true">' + escapeHTML(t("assistant")) + "</div>";
    if (safetyEscalation) {
      var reasons = (safetyReasons || []).length ? safetyReasons : [t("safetyDisclaimer")];
      html +=
        '<div class="safety-disclaimer" role="alert">' +
        '<strong class="safety-title">' + escapeHTML(t("safetyTitle")) + "</strong>" +
        reasons
          .map(function (reason) {
            return "<p>" + escapeHTML(reason) + "</p>";
          })
          .join("") +
        "</div>";
    }
    html +=
      '<div class="message-bubble">' +
      linkCitations(formatResponse(text), byNumber) +
      "</div>";
    if (citations && citations.length) {
      html += sourcesHTML(citations);
    }

    el.innerHTML = html;
    chatContainer.appendChild(el);
    // Show the start of the answer, not its end.
    requestAnimationFrame(function () {
      el.scrollIntoView({ block: "start", behavior: "smooth" });
    });
    return el;
  }

  /** Turn "[2]" in rendered text into a button that opens the source. */
  function linkCitations(html, byNumber) {
    // Any space before the marker is dropped so the number hugs its claim.
    return html.replace(/[ \u00a0]*\[(\d+)\]/g, function (whole, number) {
      var c = byNumber[number];
      if (!c) return whole;
      // The word joiner keeps the number on the same line as the claim's last word.
      return (
        '&#8288;<button type="button" class="cite cite--' + escapeHTML(c.group) + '" data-cite="' + number + '"' +
        ' aria-label="' + escapeHTML(t("openSource") + " " + number + ": " + c.authors + " " + c.year) + '">' +
        number +
        "</button>"
      );
    });
  }

  function sourcesHTML(citations) {
    var html =
      '<details class="sources">' +
      '<summary class="sources-summary">' +
        escapeHTML(t("sources")) + " (" + citations.length + ")" +
        '<span class="chevron" aria-hidden="true"></span>' +
      "</summary>";
    GROUP_ORDER.forEach(function (group) {
      var items = citations.filter(function (c) {
        return c.group === group;
      });
      if (!items.length) return;
      html +=
        '<div class="sources-group sources-group--' + group + '">' +
        '<h3 class="sources-group-title">' + escapeHTML(t(GROUP_KEYS[group])) + "</h3><ul>";
      items.forEach(function (c) {
        html +=
          '<li><button type="button" class="source-row" data-cite="' + c.number + '">' +
            '<span class="cite cite--' + escapeHTML(c.group) + '" aria-hidden="true">' + c.number + "</span>" +
            '<span class="source-row-text">' +
              '<span class="source-row-title">' + escapeHTML(c.authors + " " + c.year) + "</span>" +
              '<span class="source-row-meta">' + escapeHTML(studyMeta(c)) + "</span>" +
            "</span>" +
          "</button></li>";
      });
      html += "</ul></div>";
    });
    return html + "</details>";
  }

  function studyMeta(c) {
    var size = c.sample_size
      ? c.sample_size.toLocaleString(MedGraphI18n.getLang()) + " " + t("participants")
      : t("sizeNotStated");
    return phrase(c.design) + " · " + size;
  }

  // ============================================================
  // Citation card
  // ============================================================

  function handleChatClick(e) {
    var trigger = e.target.closest("[data-cite]");
    if (!trigger) return;
    var message = trigger.closest(".message-assistant");
    var citation = message && message._citations && message._citations[trigger.getAttribute("data-cite")];
    if (citation) {
      openCitation(citation, trigger);
    }
  }

  function openCitation(c, trigger) {
    citeTrigger = trigger;
    citeSheet.className = "cite-sheet cite-sheet--" + c.group;
    citeGroup.textContent = c.number + " · " + t(GROUP_KEYS[c.group] || "sources");
    citeTitle.textContent = c.title;

    var html =
      '<p class="cite-byline">' + escapeHTML(c.authors + ", " + c.year) + "</p>" +
      '<p class="cite-meta">' + escapeHTML(studyMeta(c)) + "</p>";

    if (c.matched_attributes && c.matched_attributes.length) {
      html +=
        '<div class="cite-match"><span class="cite-match-label">' + escapeHTML(t("matchesYou")) + "</span>" +
        c.matched_attributes
          .map(function (a) {
            return '<span class="cite-chip">' + escapeHTML(phrase(a)) + "</span>";
          })
          .join("") +
        "</div>";
    }

    var facts = [];
    if (c.cohort_summary) facts.push([t("whoWasStudied"), c.cohort_summary]);
    if (c.countries && c.countries.length) {
      facts.push([t("studiedIn"), c.countries.map(phrase).join(", ")]);
    }
    if (facts.length) {
      html +=
        '<dl class="cite-facts">' +
        facts
          .map(function (f) {
            return "<div><dt>" + escapeHTML(f[0]) + "</dt><dd>" + escapeHTML(f[1]) + "</dd></div>";
          })
          .join("") +
        "</dl>";
    }

    html += '<h3 class="cite-section">' + escapeHTML(t("whatItSays")) + "</h3>";
    var quotes = (c.quotes && c.quotes.length)
      ? c.quotes
      : (c.passages || []).map(function (text) {
          return { text: text };
        });
    quotes.forEach(function (q) {
      html += '<figure class="cite-quote-block">';
      if (q.section && q.section !== "Abstract") {
        html += '<figcaption class="cite-quote-section">' + escapeHTML(q.section) + "</figcaption>";
      }
      html += '<blockquote class="cite-quote">' + escapeHTML(q.text) + "</blockquote>";
      html += '<div class="cite-quote-links">';
      // Plain links, followed by a real click: browsers ignore
      // scroll-to-text links that are opened by script.
      if (/^https:\/\/pmc\.ncbi\.nlm\.nih\.gov\//.test(q.pmc_url || "")) {
        html += openLink(q.pmc_url, t("openOnPmc"), "cite-open cite-open--primary");
      }
      if (/^\/paper\//.test(q.reader_url || "")) {
        html += openLink(q.reader_url, t("openInReader"), q.pmc_url ? "cite-open" : "cite-open cite-open--primary");
      }
      html += "</div></figure>";
    });

    if (/^https:\/\//.test(c.url || "")) {
      html +=
        '<a class="cite-link" href="' + escapeHTML(c.url) + '" target="_blank" rel="noopener noreferrer">' +
        escapeHTML(t("readStudy")) +
        ' <span aria-hidden="true">&#8599;</span><span class="sr-only"> (' + escapeHTML(t("opensNewTab")) + ")</span></a>";
    }

    citeContent.innerHTML = html;
    citeBackdrop.hidden = false;
    citeSheet.hidden = false;
    document.getElementById("citeBody").scrollTop = 0;
    citeClose.focus();
  }

  function openLink(url, label, className) {
    return (
      '<a class="' + className + '" href="' + escapeHTML(url) + '" target="_blank" rel="noopener noreferrer">' +
      escapeHTML(label) +
      ' <span aria-hidden="true">&#8599;</span><span class="sr-only"> (' + escapeHTML(t("opensNewTab")) + ")</span></a>"
    );
  }

  function closeCitation() {
    if (citeSheet.hidden) return;
    citeSheet.hidden = true;
    citeBackdrop.hidden = true;
    if (citeTrigger && document.body.contains(citeTrigger)) {
      citeTrigger.focus();
    }
    citeTrigger = null;
  }

  function handleSheetKeys(e) {
    if (citeSheet.hidden) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeCitation();
      return;
    }
    if (e.key !== "Tab") return;
    // Keep keyboard focus inside the open card.
    var focusable = citeSheet.querySelectorAll("button, a[href]");
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    } else if (!citeSheet.contains(document.activeElement)) {
      e.preventDefault();
      first.focus();
    }
  }

  // ============================================================
  // Utilities
  // ============================================================

  function setInputEnabled(enabled) {
    var usable = enabled && !!selectedPersona;
    messageInput.disabled = !usable;
    sendBtn.disabled = !usable;
    micBtn.disabled = !usable || !recognition;
    document.querySelectorAll(".patient-btn").forEach(function (btn) {
      btn.disabled = !enabled;
    });
  }

  function scrollToBottom() {
    requestAnimationFrame(function () {
      // On a phone the whole page scrolls; on a wide screen only the conversation does.
      if (getComputedStyle(chatContainer).overflowY === "visible") {
        window.scrollTo(0, document.documentElement.scrollHeight);
      } else {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      }
    });
  }

  function escapeHTML(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML.replace(/"/g, "&quot;");
  }

  function formatResponse(text) {
    if (!text) return "";
    // The answer is model output: neutralise raw HTML before rendering Markdown.
    return marked.parse(text.replace(/&/g, "&amp;").replace(/</g, "&lt;"));
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function newSessionId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
})();

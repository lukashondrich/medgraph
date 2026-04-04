/* ==========================================================
   medgraph Health Navigator - Frontend Client
   WCAG 2.2 AA · DE/EN · Speech input · Dark/High-contrast
   ========================================================== */

(function () {
  "use strict";

  // --- i18n shorthand ---
  var t = MedGraphI18n.t;

  // --- State ---
  var sessionId = crypto.randomUUID ? crypto.randomUUID() : generateUUID();
  var isProcessing = false;
  var selectedPatientId = null;
  var isListening = false;
  var recognition = null;

  // --- DOM refs ---
  var chatContainer = document.getElementById("chatContainer");
  var chatForm = document.getElementById("chatForm");
  var messageInput = document.getElementById("messageInput");
  var sendBtn = document.getElementById("sendBtn");
  var patientGallery = document.getElementById("patientGallery");
  var patientCard = document.getElementById("patientCard");
  var patientName = document.getElementById("patientName");
  var patientDemo = document.getElementById("patientDemo");
  var patientHeadline = document.getElementById("patientHeadline");
  var patientTags = document.getElementById("patientTags");
  var clearPatientBtn = document.getElementById("clearPatient");
  var langToggle = document.getElementById("langToggle");
  var themeToggle = document.getElementById("themeToggle");
  var contrastToggle = document.getElementById("contrastToggle");
  var micBtn = document.getElementById("micBtn");
  var srAnnouncements = document.getElementById("srAnnouncements");
  var modelIndicator = document.getElementById("modelIndicator");
  var modelIndicatorLabel = document.getElementById("modelIndicatorLabel");

  // --- Init ---
  initTheme();
  initContrast();
  initSpeechRecognition();
  MedGraphI18n.applyTranslations();
  checkOllamaStatus();
  setInterval(checkOllamaStatus, 30000);

  chatForm.addEventListener("submit", handleSubmit);
  clearPatientBtn.addEventListener("click", clearPatient);
  langToggle.addEventListener("click", toggleLanguage);
  themeToggle.addEventListener("click", toggleTheme);
  contrastToggle.addEventListener("click", toggleContrast);
  micBtn.addEventListener("click", toggleMic);

  loadPatientGallery();

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
    var label =
      theme === "dark" ? t("lightMode") : t("darkMode");
    themeToggle.setAttribute("aria-label", label);
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
    var current = MedGraphI18n.getLang();
    var next = current === "en" ? "de" : "en";
    MedGraphI18n.setLanguage(next);

    // Update speech recognition language
    if (recognition) {
      recognition.lang = next === "de" ? "de-DE" : "en-US";
    }

    // Update dynamic aria-labels that aren't covered by data-i18n
    themeToggle.setAttribute(
      "aria-label",
      document.documentElement.getAttribute("data-theme") === "dark"
        ? t("lightMode")
        : t("darkMode")
    );
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
    recognition.lang =
      MedGraphI18n.getLang() === "de" ? "de-DE" : "en-US";

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
        // Already started or other error
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
    // Clear then set to force re-announcement
    srAnnouncements.textContent = "";
    requestAnimationFrame(function () {
      srAnnouncements.textContent = text;
    });
  }

  // ============================================================
  // Ollama status polling
  // ============================================================

  async function checkOllamaStatus() {
    try {
      var resp = await fetch("/api/ollama-status");
      var data = await resp.json();
      updateModelIndicator(data.available, data.model);
    } catch (e) {
      updateModelIndicator(false, null);
    }
  }

  function updateModelIndicator(available, modelName) {
    if (!modelIndicator || !modelIndicatorLabel) return;
    modelIndicator.classList.remove("local", "cloud");
    if (available) {
      modelIndicator.classList.add("local");
      modelIndicatorLabel.textContent = t("modelLocal");
    } else {
      modelIndicator.classList.add("cloud");
      modelIndicatorLabel.textContent = t("modelCloud");
    }
  }

  // ============================================================
  // UUID fallback
  // ============================================================

  function generateUUID() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
      /[xy]/g,
      function (c) {
        var r = (Math.random() * 16) | 0;
        var v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      }
    );
  }

  // ============================================================
  // Patient Gallery
  // ============================================================

  async function loadPatientGallery() {
    try {
      var resp = await fetch("/api/patients");
      var patients = await resp.json();
      renderGallery(patients);
    } catch (err) {
      console.error("Failed to load patients:", err);
      patientGallery.innerHTML =
        '<span class="gallery-error" role="alert">' +
        escapeHTML(t("galleryError")) +
        "</span>";
    }
  }

  function renderGallery(patients) {
    patientGallery.innerHTML = "";
    patients.forEach(function (p) {
      var btn = document.createElement("button");
      btn.className = "patient-btn";
      btn.setAttribute("data-id", p.patient_id);
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", p.name + ", " + p.age + (p.sex === "F" ? "F" : "M"));
      btn.innerHTML =
        "<strong>" +
        escapeHTML(p.name) +
        "</strong> " +
        '<span class="patient-btn-meta">' +
        p.age +
        (p.sex === "F" ? "F" : "M") +
        "</span>";
      btn.addEventListener("click", function () {
        selectPatient(p);
      });
      patientGallery.appendChild(btn);
    });
  }

  function selectPatient(p) {
    selectedPatientId = p.patient_id;

    // Update aria-pressed on all patient buttons
    document.querySelectorAll(".patient-btn").forEach(function (btn) {
      var isSelected = btn.getAttribute("data-id") === p.patient_id;
      btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
    });

    // Show patient card
    patientCard.style.display = "block";
    patientName.textContent = p.name;
    patientDemo.textContent = p.age + (p.sex === "F" ? "F" : "M");
    patientHeadline.textContent = p.headline;

    // Render condition tags
    patientTags.innerHTML = "";
    (p.condition_tags || []).slice(0, 6).forEach(function (tag) {
      var el = document.createElement("span");
      el.className = "condition-tag";
      el.setAttribute("role", "listitem");
      el.textContent = tag;
      patientTags.appendChild(el);
    });
    if (p.condition_tags && p.condition_tags.length > 6) {
      var more = document.createElement("span");
      more.className = "condition-tag condition-tag-more";
      more.setAttribute("role", "listitem");
      more.textContent = "+" + (p.condition_tags.length - 6) + " more";
      patientTags.appendChild(more);
    }

    // Reset session for new patient
    sessionId = crypto.randomUUID ? crypto.randomUUID() : generateUUID();

    announce(p.name + " " + t("selectPatient"));
  }

  function clearPatient() {
    selectedPatientId = null;
    patientCard.style.display = "none";
    document.querySelectorAll(".patient-btn").forEach(function (btn) {
      btn.setAttribute("aria-pressed", "false");
    });
    sessionId = crypto.randomUUID ? crypto.randomUUID() : generateUUID();
    announce(t("clearPatient"));
  }

  // ============================================================
  // Submit handler
  // ============================================================

  async function handleSubmit(e) {
    e.preventDefault();

    var message = messageInput.value.trim();
    if (!message || isProcessing) return;

    isProcessing = true;
    setInputEnabled(false);

    // Remove welcome message on first send
    var welcome = chatContainer.querySelector(".welcome-message");
    if (welcome) {
      welcome.setAttribute("aria-hidden", "true");
      welcome.style.display = "none";
    }

    appendUserMessage(message);
    messageInput.value = "";

    var pipelineEl = createPipelineStatus();
    chatContainer.appendChild(pipelineEl);
    scrollToBottom();

    try {
      await streamChat(message, pipelineEl);
    } catch (err) {
      var errorEl = appendAssistantMessage(t("errorGeneric"), false);
      if (errorEl) {
        errorEl.setAttribute("role", "alert");
      }
      console.error("Chat stream error:", err);
    }

    isProcessing = false;
    setInputEnabled(true);
    messageInput.focus();
  }

  // ============================================================
  // SSE streaming
  // ============================================================

  async function streamChat(message, pipelineEl) {
    var body = {
      message: message,
      session_id: sessionId,
      language: MedGraphI18n.getLang(),
    };
    if (selectedPatientId) {
      body.patient_id = selectedPatientId;
    }

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
        handleSSEEvent(events.parsed[i], pipelineEl);
      }
    }
  }

  // ============================================================
  // Parse SSE
  // ============================================================

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

  // ============================================================
  // Handle SSE events
  // ============================================================

  function handleSSEEvent(event, pipelineEl) {
    switch (event.type) {
      case "routing":
        updatePipelineRouting(pipelineEl, event.data);
        if (event.data.model_source) {
          updateModelIndicator(event.data.model_source === "local", null);
        }
        scrollToBottom();
        break;

      case "specialist":
        updatePipelineSpecialist(pipelineEl, event.data);
        scrollToBottom();
        break;

      case "synthesizing":
        updatePipelineSynthesizing(pipelineEl);
        scrollToBottom();
        break;

      case "response":
        var synthBadge = pipelineEl.querySelector(
          '[data-agent="synthesizer"]'
        );
        if (synthBadge) {
          synthBadge.className = "agent-badge done";
          synthBadge.innerHTML =
            '<span class="agent-badge-icon" aria-hidden="true">&#10003;</span> ' +
            t("synthesizing");
          synthBadge.setAttribute(
            "aria-label",
            t("synthesizing") + " — done"
          );
        }

        if (event.data.session_id) {
          sessionId = event.data.session_id;
        }

        appendAssistantMessage(
          event.data.content,
          event.data.safety_escalation
        );
        scrollToBottom();
        break;

      case "error":
        var errorMsg =
          t("errorGeneric") +
          (event.data.message ? " " + event.data.message : "");
        var errEl = appendAssistantMessage(errorMsg, false);
        if (errEl) errEl.setAttribute("role", "alert");
        scrollToBottom();
        break;

      case "done":
        if (event.data && event.data.session_id) {
          sessionId = event.data.session_id;
        }
        break;
    }
  }

  // ============================================================
  // DOM builders
  // ============================================================

  function appendUserMessage(text) {
    var el = document.createElement("article");
    el.className = "message message-user";
    el.setAttribute("aria-label", t("messageFrom") + " " + t("you"));
    el.innerHTML =
      '<div class="message-label" aria-hidden="true">' +
      escapeHTML(t("you")) +
      "</div>" +
      '<div class="message-bubble">' +
      escapeHTML(text) +
      "</div>";
    chatContainer.appendChild(el);
    scrollToBottom();
  }

  function appendAssistantMessage(text, safetyEscalation) {
    var el = document.createElement("article");
    el.className = "message message-assistant";
    el.setAttribute("aria-label", t("responseFrom"));

    var html =
      '<div class="message-label" aria-hidden="true">' +
      escapeHTML(t("assistant")) +
      "</div>" +
      '<div class="message-bubble">' +
      formatResponse(text) +
      "</div>";

    if (safetyEscalation) {
      html +=
        '<div class="safety-disclaimer" role="alert">' +
        escapeHTML(t("safetyDisclaimer")) +
        "</div>";
    }

    el.innerHTML = html;
    chatContainer.appendChild(el);
    scrollToBottom();
    return el;
  }

  function createPipelineStatus() {
    var el = document.createElement("div");
    el.className = "pipeline-status";
    el.setAttribute("role", "status");
    el.setAttribute("aria-label", t("agentPipeline"));

    // Determine initial local/cloud class from model indicator state
    var modelSourceClass = "";
    if (modelIndicator) {
      modelSourceClass = modelIndicator.classList.contains("local") ? "local" : "cloud";
    }

    el.innerHTML =
      '<div class="pipeline-card">' +
        '<div class="pipeline-title" aria-hidden="true">' +
          escapeHTML(t("agentPipeline")) +
        "</div>" +
        '<div class="pipeline-row" id="pipelineRouterRow">' +
          '<span class="agent-badge processing ' + modelSourceClass + '" data-agent="router" role="status" aria-label="' + escapeHTML(t("routerThinking")) + ' — processing">' +
            '<span class="spinner" aria-hidden="true"></span> ' +
            escapeHTML(t("routerThinking")) +
            '<span class="badge-timer">0s</span>' +
          "</span>" +
        "</div>" +
        '<div class="pipeline-row" id="pipelineSpecialistRow" style="display:none"></div>' +
        '<div class="pipeline-row" id="pipelineSynthRow" style="display:none"></div>' +
        '<div class="pipeline-reasoning" id="pipelineReasoning"></div>' +
      "</div>";

    // Start elapsed timer
    var timerStart = Date.now();
    var timerInterval = setInterval(function () {
      var badge = el.querySelector('[data-agent="router"] .badge-timer');
      if (badge) {
        var elapsed = Math.floor((Date.now() - timerStart) / 1000);
        badge.textContent = elapsed + "s";
      }
    }, 1000);
    el._pipelineTimerInterval = timerInterval;

    return el;
  }

  function updatePipelineRouting(pipelineEl, data) {
    // Initial "routing in progress" — already handled by createPipelineStatus
    if (data.status === "processing" && !data.agents) {
      return;
    }

    // Router completed — stop timer, mark done, show reasoning + specialists
    if (data.agents) {
      // Stop the elapsed timer
      if (pipelineEl._pipelineTimerInterval) {
        clearInterval(pipelineEl._pipelineTimerInterval);
        pipelineEl._pipelineTimerInterval = null;
      }

      // Mark router badge as done with local/cloud color
      var routerBadge = pipelineEl.querySelector('[data-agent="router"]');
      if (routerBadge) {
        var timerEl = routerBadge.querySelector(".badge-timer");
        var frozenTime = timerEl ? timerEl.textContent : "0s";
        var sourceClass = (data.model_source === "local") ? "local" : "cloud";
        routerBadge.className = "agent-badge done " + sourceClass;
        routerBadge.innerHTML =
          '<span class="agent-badge-icon" aria-hidden="true">&#10003;</span> ' +
          escapeHTML(t("routing")) +
          '<span class="badge-timer">' + escapeHTML(frozenTime) + '</span>';
      }

      // Show reasoning callout with typewriter reveal
      var reasoningEl = pipelineEl.querySelector("#pipelineReasoning");
      if (reasoningEl && data.reasoning) {
        reasoningEl.classList.add("visible");
        typewriterReveal(reasoningEl, data.reasoning, 18);
      }

      // Populate specialist row
      var specialistRow = pipelineEl.querySelector("#pipelineSpecialistRow");
      if (specialistRow && data.agents.length > 0) {
        specialistRow.innerHTML = "";
        data.agents.forEach(function (agent) {
          var badge = document.createElement("span");
          badge.className = "agent-badge processing";
          badge.setAttribute("data-agent", agent);
          badge.setAttribute("role", "status");
          badge.setAttribute("aria-label", formatAgentName(agent) + " — processing");
          badge.innerHTML =
            '<span class="spinner" aria-hidden="true"></span> ' +
            escapeHTML(formatAgentName(agent));
          specialistRow.appendChild(badge);
        });
        specialistRow.style.display = "";
      }

      announce(
        t("routing") + ": " + data.agents.map(formatAgentName).join(", ")
      );
    }
  }

  function updatePipelineSpecialist(pipelineEl, data) {
    if (data.status === "done") {
      var badge = pipelineEl.querySelector(
        '.agent-badge[data-agent="' + data.agent + '"]'
      );
      if (badge) {
        badge.className = "agent-badge done";
        badge.innerHTML =
          '<span class="agent-badge-icon" aria-hidden="true">&#10003;</span> ' +
          escapeHTML(formatAgentName(data.agent));
        badge.setAttribute(
          "aria-label",
          formatAgentName(data.agent) + " — done"
        );
      }
    }
  }

  function updatePipelineSynthesizing(pipelineEl) {
    var synthRow = pipelineEl.querySelector("#pipelineSynthRow");
    if (!synthRow) return;

    if (synthRow.querySelector('[data-agent="synthesizer"]')) return;

    var badge = document.createElement("span");
    badge.className = "agent-badge processing";
    badge.setAttribute("data-agent", "synthesizer");
    badge.setAttribute("role", "status");
    badge.setAttribute("aria-label", t("synthesizing") + " — processing");
    badge.innerHTML =
      '<span class="spinner" aria-hidden="true"></span> ' +
      escapeHTML(t("synthesizing"));
    synthRow.appendChild(badge);
    synthRow.style.display = "";

    announce(t("synthesizing"));
  }

  // ============================================================
  // Utilities
  // ============================================================

  function setInputEnabled(enabled) {
    messageInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    micBtn.disabled = !enabled && !recognition;
  }

  function scrollToBottom() {
    requestAnimationFrame(function () {
      chatContainer.scrollTop = chatContainer.scrollHeight;
    });
  }

  function typewriterReveal(el, text, msPerChar) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = text;
      return;
    }
    el.textContent = "";
    var i = 0;
    var interval = setInterval(function () {
      var chunk = text.slice(i, i + 3);
      el.textContent += chunk;
      i += 3;
      if (i >= text.length) {
        clearInterval(interval);
        el.textContent = text;
      }
      scrollToBottom();
    }, msPerChar);
  }

  function escapeHTML(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function formatResponse(text) {
    if (!text) return "";
    return marked.parse(text);
  }

  function formatAgentName(agent) {
    var keys = {
      symptom: "agentSymptom",
      medication: "agentMedication",
      lifestyle: "agentLifestyle",
      evidence: "agentEvidence",
      drug_check: "agentDrugCheck",
    };
    return keys[agent] ? t(keys[agent]) : capitalize(agent);
  }

  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
})();

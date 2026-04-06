/* ==========================================================
   medgraph — Internationalization (DE/EN)
   ========================================================== */

var MedGraphI18n = (function () {
  "use strict";

  var translations = {
    en: {
      pageTitle: "medgraph \u2014 Patient-Aware Health Navigator",
      appTitle: "medgraph",
      appTitleAccent: "Health Navigator",
      appSubtitle: "Patient-aware multiagent healthcare guidance",
      selectPatient: "Select a patient:",
      clearPatient: "Clear selected patient",
      chatMessages: "Chat messages",
      welcomeTitle:
        "Welcome! Select a patient above, then ask a health question.",
      welcomeCapabilities:
        'I can help with <strong>symptoms</strong>, <strong>medications</strong>, <strong>lifestyle</strong>, <strong>clinical evidence</strong>, and <strong>drug interactions</strong>.',
      welcomeDisclaimer:
        "I am an AI assistant and cannot diagnose or prescribe. Always consult a healthcare provider for medical concerns.",
      inputLabel: "Health question",
      inputPlaceholder: "Ask a health question\u2026",
      send: "Send",
      you: "You",
      assistant: "medgraph",
      agentPipeline: "Agent Pipeline",
      routing: "Routing",
      routerThinking: "Thinking",
      synthesizing: "Synthesizing",
      errorGeneric: "Sorry, something went wrong. Please try again.",
      safetyDisclaimer:
        "Important: Please consult a qualified healthcare provider for personalized medical advice. This AI assistant cannot diagnose conditions or prescribe treatments.",
      skipToChat: "Skip to chat",
      micStart: "Start voice input",
      micStop: "Stop voice input",
      micUnsupported: "Voice input is not supported in this browser",
      listening: "Listening\u2026",
      langToggle: "DE",
      langToggleLabel: "Auf Deutsch wechseln",
      darkMode: "Dark mode",
      lightMode: "Light mode",
      highContrast: "Toggle high contrast",
      galleryError: "Failed to load patients",
      agentSymptom: "Symptom",
      agentMedication: "Medication",
      agentLifestyle: "Lifestyle",
      agentEvidence: "Evidence",
      agentDrugCheck: "Drug Check",
      messageFrom: "Message from",
      responseFrom: "Response from medgraph",
      modelLocal: "Local",
      modelCloud: "Cloud",
      modelChecking: "Checking...",
      patientInfoLabel: "About patient data",
      patientInfoText: "Synthetic patients generated with Synthea (FHIR R4). No real patient data is used.",
    },
    de: {
      pageTitle: "medgraph \u2014 Patientenbezogener Gesundheitsnavigator",
      appTitle: "medgraph",
      appTitleAccent: "Gesundheitsnavigator",
      appSubtitle:
        "Patientenbezogene multiagenten-gest\u00FCtzte Gesundheitsberatung",
      selectPatient: "Patient ausw\u00E4hlen:",
      clearPatient: "Ausgew\u00E4hlten Patienten entfernen",
      chatMessages: "Chatnachrichten",
      welcomeTitle:
        "Willkommen! W\u00E4hlen Sie oben einen Patienten aus und stellen Sie eine Gesundheitsfrage.",
      welcomeCapabilities:
        'Ich kann bei <strong>Symptomen</strong>, <strong>Medikamenten</strong>, <strong>Lebensstil</strong>, <strong>klinischer Evidenz</strong> und <strong>Wechselwirkungen</strong> helfen.',
      welcomeDisclaimer:
        "Ich bin ein KI-Assistent und kann weder diagnostizieren noch verschreiben. Bitte konsultieren Sie bei gesundheitlichen Bedenken immer einen Arzt.",
      inputLabel: "Gesundheitsfrage",
      inputPlaceholder: "Stellen Sie eine Gesundheitsfrage\u2026",
      send: "Senden",
      you: "Sie",
      assistant: "medgraph",
      agentPipeline: "Agenten-Pipeline",
      routing: "Weiterleitung",
      routerThinking: "Denke nach",
      synthesizing: "Synthese",
      errorGeneric:
        "Entschuldigung, etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.",
      safetyDisclaimer:
        "Wichtig: Bitte konsultieren Sie einen qualifizierten Arzt f\u00FCr eine individuelle medizinische Beratung. Dieser KI-Assistent kann keine Diagnosen stellen oder Behandlungen verschreiben.",
      skipToChat: "Zum Chat springen",
      micStart: "Spracheingabe starten",
      micStop: "Spracheingabe stoppen",
      micUnsupported:
        "Spracheingabe wird in diesem Browser nicht unterst\u00FCtzt",
      listening: "H\u00F6re zu\u2026",
      langToggle: "EN",
      langToggleLabel: "Switch to English",
      darkMode: "Dunkelmodus",
      lightMode: "Hellmodus",
      highContrast: "Hohen Kontrast umschalten",
      galleryError: "Patienten konnten nicht geladen werden",
      agentSymptom: "Symptome",
      agentMedication: "Medikamente",
      agentLifestyle: "Lebensstil",
      agentEvidence: "Evidenz",
      agentDrugCheck: "Wechselwirkungen",
      messageFrom: "Nachricht von",
      responseFrom: "Antwort von medgraph",
      modelLocal: "Lokal",
      modelCloud: "Cloud",
      modelChecking: "Pr\u00FCfe...",
      patientInfoLabel: "\u00DCber Patientendaten",
      patientInfoText: "Synthetische Patienten, generiert mit Synthea (FHIR R4). Es werden keine echten Patientendaten verwendet.",
    },
  };

  var currentLang = localStorage.getItem("medgraph-lang") || "en";

  /** Get a translated string by key. Falls back to English, then to the key itself. */
  function t(key) {
    return (
      (translations[currentLang] && translations[currentLang][key]) ||
      (translations.en && translations.en[key]) ||
      key
    );
  }

  /** Switch the active language, persist, update lang attribute, re-apply translations. */
  function setLanguage(lang) {
    if (!translations[lang]) return;
    currentLang = lang;
    localStorage.setItem("medgraph-lang", lang);
    document.documentElement.setAttribute("lang", lang);
    document.title = t("pageTitle");
    applyTranslations();
  }

  /** Scan the DOM and apply translations based on data-i18n-* attributes. */
  function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n-html"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
    });
  }

  /** Return the current language code. */
  function getLang() {
    return currentLang;
  }

  // Initialize lang attribute on load
  document.documentElement.setAttribute("lang", currentLang);

  return {
    t: t,
    setLanguage: setLanguage,
    applyTranslations: applyTranslations,
    getLang: getLang,
  };
})();

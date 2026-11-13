/* ==========================================================
   pH Companion — Internationalization (DE/EN)
   ========================================================== */

var MedGraphI18n = (function () {
  "use strict";

  var translations = {
    en: {
      pageTitle: "pH Companion — your test result, explained",
      appTitle: "pH",
      appTitleAccent: "Companion",
      appSubtitle: "Your test result, explained with studies that fit you",
      settings: "Settings",
      selectPersona: "Choose a profile",
      personaSelected: "profile selected",
      personaInfoLabel: "About these profiles",
      personaInfoText: "Demo profiles. No real personal data is used.",
      galleryError: "Could not load the profiles",
      yourTest: "Your test result",
      chooseReading: "Choose a test result",
      readingSelected: "Test result selected",
      readConfidence: "Reading confidence",
      readingUnclear: "unclear strip",
      readingUncertain: "Uncertain reading — consider retesting",
      takenAt: "taken at",
      newReading: "New test result",
      chatMessages: "Conversation",
      welcomeTitle:
        "Choose a profile, then a test result. I will explain what the reading means for that woman.",
      welcomeCapabilities:
        "Every statement links to the <strong>study it comes from</strong>, including <strong>studies in women like her</strong>.",
      welcomeDisclaimer:
        "I am an AI assistant and cannot diagnose or prescribe. A home pH test cannot confirm or rule out an infection.",
      inputLabel: "Question about your result",
      inputPlaceholder: "Ask about your result…",
      send: "Send",
      sendLabel: "Send question",
      you: "You",
      assistant: "pH Companion",
      messageFrom: "Message from",
      responseFrom: "Answer from pH Companion",
      errorGeneric: "Sorry, something went wrong. Please try again.",
      safetyDisclaimer:
        "Please see a doctor or other qualified clinician about this. pH Companion cannot diagnose conditions or prescribe treatments.",
      skipToChat: "Skip to conversation",
      micStart: "Start voice input",
      micStop: "Stop voice input",
      micUnsupported: "Voice input is not supported in this browser",
      listening: "Listening…",
      langToggle: "DE",
      langToggleLabel: "Auf Deutsch wechseln",
      darkMode: "Dark mode",
      lightMode: "Light mode",
      highContrast: "Toggle high contrast",

      // Profile details
      profAge: "Age",
      profAncestry: "Ancestry",
      profCountry: "Lives in",
      profMenopause: "Menopausal status",
      profPregnancy: "Pregnancy",
      profCycle: "Cycle",
      profContraception: "Hormonal contraception",
      profHrt: "Hormone therapy",
      profAntibiotics: "Antibiotics recently",
      profSymptoms: "Symptoms",
      profHistory: "History",
      valNone: "none",
      valYes: "yes",
      valNo: "no",
      valRegular: "regular",
      valIrregular: "irregular",
      valDay: "day",
      premenopausal: "before menopause",
      perimenopausal: "around menopause",
      postmenopausal: "after menopause",
      not_pregnant: "not pregnant",
      first_trimester: "pregnant, first trimester",
      second_trimester: "pregnant, second trimester",
      third_trimester: "pregnant, third trimester",

      // Lookup steps
      lookingUp: "Looking things up",
      lookedUp: "What I looked up",
      stepProcessing: "in progress",
      stepDone: "done",
      srcPlan: "Deciding what to look up",
      srcSafetyRules: "Safety check",
      srcGuidelines: "Guidelines",
      srcReferenceRanges: "Reference ranges",
      srcStudyLibrary: "Study library",
      srcWriter: "Writing your answer",
      detailSafetyNone: "No urgent flags",
      detailSafetyFired: "{n} reason to see a clinician",
      detailGuidelines: "{found} relevant",
      safetyTitle: "Please see a clinician",
      groupSafety: "Behind the safety advice",
      detailRanges: "{found} statements for: {query}",
      detailSearched: "Searched",
      detailMore: "+{n} more",
      detailStudies: "{used} of {found} studies used",
      detailMatched: "{matched} in women like you",
      detailError: "Search failed; answering without it",
      summarySources: "Checked {n} sources",
      summaryStudies: "{used} studies",

      // Citations
      sources: "Sources",
      groupMatched: "Studies in women like you",
      groupOverall: "Best overall evidence",
      groupRange: "Reference ranges",
      groupGuideline: "Guidelines",
      openSource: "Open source",
      closeSource: "Close source",
      participants: "participants",
      sizeNotStated: "size not stated",
      matchesYou: "Matches you",
      studiedIn: "Run in",
      whoWasStudied: "Who was studied",
      whatItSays: "What the study says",
      readStudy: "Read the study",
      opensNewTab: "opens in a new tab",
    },
    de: {
      pageTitle: "pH Companion — Ihr Testergebnis, erklärt",
      appTitle: "pH",
      appTitleAccent: "Companion",
      appSubtitle: "Ihr Testergebnis, erklärt mit Studien, die zu Ihnen passen",
      settings: "Einstellungen",
      selectPersona: "Profil wählen",
      personaSelected: "Profil ausgewählt",
      personaInfoLabel: "Über diese Profile",
      personaInfoText: "Demo-Profile. Es werden keine echten persönlichen Daten verwendet.",
      galleryError: "Die Profile konnten nicht geladen werden",
      yourTest: "Ihr Testergebnis",
      chooseReading: "Testergebnis wählen",
      readingSelected: "Testergebnis ausgewählt",
      readConfidence: "Messsicherheit",
      readingUnclear: "Streifen unklar",
      readingUncertain: "Unsichere Messung — Test am besten wiederholen",
      takenAt: "gemessen um",
      newReading: "Neues Testergebnis",
      chatMessages: "Gespräch",
      welcomeTitle:
        "Wählen Sie ein Profil und dann ein Testergebnis. Ich erkläre, was der Wert für diese Frau bedeutet.",
      welcomeCapabilities:
        "Jede Aussage ist mit der <strong>Studie verknüpft, aus der sie stammt</strong> — auch mit <strong>Studien an Frauen wie ihr</strong>.",
      welcomeDisclaimer:
        "Ich bin ein KI-Assistent und kann weder diagnostizieren noch verschreiben. Ein pH-Selbsttest kann eine Infektion weder bestätigen noch ausschließen.",
      inputLabel: "Frage zu Ihrem Ergebnis",
      inputPlaceholder: "Frage zu Ihrem Ergebnis…",
      send: "Senden",
      sendLabel: "Frage senden",
      you: "Sie",
      assistant: "pH Companion",
      messageFrom: "Nachricht von",
      responseFrom: "Antwort von pH Companion",
      errorGeneric: "Entschuldigung, etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.",
      safetyDisclaimer:
        "Bitte besprechen Sie das mit einer Ärztin, einem Arzt oder einer anderen Fachperson. pH Companion kann keine Diagnosen stellen und keine Behandlungen verschreiben.",
      skipToChat: "Zum Gespräch springen",
      micStart: "Spracheingabe starten",
      micStop: "Spracheingabe beenden",
      micUnsupported: "Spracheingabe wird in diesem Browser nicht unterstützt",
      listening: "Ich höre zu…",
      langToggle: "EN",
      langToggleLabel: "Switch to English",
      darkMode: "Dunkler Modus",
      lightMode: "Heller Modus",
      highContrast: "Hohen Kontrast umschalten",

      profAge: "Alter",
      profAncestry: "Herkunft",
      profCountry: "Wohnort",
      profMenopause: "Menopause-Status",
      profPregnancy: "Schwangerschaft",
      profCycle: "Zyklus",
      profContraception: "Hormonelle Verhütung",
      profHrt: "Hormontherapie",
      profAntibiotics: "Kürzlich Antibiotika",
      profSymptoms: "Beschwerden",
      profHistory: "Vorgeschichte",
      valNone: "keine",
      valYes: "ja",
      valNo: "nein",
      valRegular: "regelmäßig",
      valIrregular: "unregelmäßig",
      valDay: "Tag",
      premenopausal: "vor der Menopause",
      perimenopausal: "um die Menopause",
      postmenopausal: "nach der Menopause",
      not_pregnant: "nicht schwanger",
      first_trimester: "schwanger, erstes Trimester",
      second_trimester: "schwanger, zweites Trimester",
      third_trimester: "schwanger, drittes Trimester",

      lookingUp: "Ich schlage nach",
      lookedUp: "Was ich nachgeschlagen habe",
      stepProcessing: "läuft",
      stepDone: "fertig",
      srcPlan: "Ich überlege, wo ich nachschlage",
      srcSafetyRules: "Sicherheitsprüfung",
      srcGuidelines: "Leitlinien",
      srcReferenceRanges: "Referenzbereiche",
      srcStudyLibrary: "Studienbibliothek",
      srcWriter: "Antwort wird geschrieben",
      detailSafetyNone: "Keine dringenden Hinweise",
      detailSafetyFired: "{n} Grund für einen Arztbesuch",
      detailGuidelines: "{found} relevant",
      safetyTitle: "Bitte ärztlich abklären lassen",
      groupSafety: "Hinter dem Sicherheitshinweis",
      detailRanges: "{found} Aussagen für: {query}",
      detailSearched: "Gesucht",
      detailMore: "+{n} weitere",
      detailStudies: "{used} von {found} Studien verwendet",
      detailMatched: "{matched} an Frauen wie Ihnen",
      detailError: "Suche fehlgeschlagen; Antwort ohne diese Quelle",
      summarySources: "{n} Quellen geprüft",
      summaryStudies: "{used} Studien",

      sources: "Quellen",
      groupMatched: "Studien an Frauen wie Ihnen",
      groupOverall: "Beste Evidenz insgesamt",
      groupRange: "Referenzbereiche",
      groupGuideline: "Leitlinien",
      openSource: "Quelle öffnen",
      closeSource: "Quelle schließen",
      participants: "Teilnehmerinnen",
      sizeNotStated: "Größe nicht angegeben",
      matchesYou: "Passt zu Ihnen",
      studiedIn: "Durchgeführt in",
      whoWasStudied: "Wer untersucht wurde",
      whatItSays: "Was die Studie sagt",
      readStudy: "Studie lesen",
      opensNewTab: "öffnet in neuem Tab",
    },
  };

  // Short labels that arrive from the server in English (study designs,
  // matched attributes). Study titles, cohort descriptions and quoted
  // passages stay in the language of the paper.
  var phrases = {
    de: {
      "Meta-analysis": "Metaanalyse",
      "Systematic review": "Systematische Übersicht",
      "Guideline": "Leitlinie",
      "Randomised trial": "Randomisierte Studie",
      "Controlled trial (not randomised)": "Kontrollierte Studie (nicht randomisiert)",
      "Cohort study": "Kohortenstudie",
      "Cross-sectional study": "Querschnittsstudie",
      "Case-control study": "Fall-Kontroll-Studie",
      "Case series": "Fallserie",
      "Laboratory study": "Laborstudie",
      "Review": "Übersichtsarbeit",
      "Study": "Studie",
      "Indian ancestry": "Indische Herkunft",
      "South Asian ancestry (broader group)": "Südasiatische Herkunft (größere Gruppe)",
      "Black ancestry": "Schwarze Herkunft",
      "White European ancestry": "Weiße europäische Herkunft",
      "pregnant": "schwanger",
      "not pregnant": "nicht schwanger",
      "premenopausal": "vor der Menopause",
      "perimenopausal": "um die Menopause",
      "postmenopausal": "nach der Menopause",
      "your age group": "Ihre Altersgruppe",
      "lives in Germany": "lebt in Deutschland",
      "Indian": "Indisch",
      "Black": "Schwarz",
      "White European": "Weiß, europäisch",
      "Germany": "Deutschland",
      "India": "Indien",
      "United States": "USA",
    },
  };

  /** Translate a short server-side label; unknown text is returned unchanged. */
  function phrase(text) {
    var table = phrases[currentLang];
    return (table && table[text]) || text;
  }

  var currentLang = localStorage.getItem("medgraph-lang") || "en";

  /** Look up a key; `vars` fills {placeholders}. Falls back to English, then the key. */
  function t(key, vars) {
    var text =
      (translations[currentLang] && translations[currentLang][key]) ||
      (translations.en && translations.en[key]) ||
      key;
    if (vars) {
      Object.keys(vars).forEach(function (name) {
        text = text.split("{" + name + "}").join(String(vars[name]));
      });
    }
    return text;
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
  document.title = t("pageTitle");

  return {
    t: t,
    phrase: phrase,
    setLanguage: setLanguage,
    applyTranslations: applyTranslations,
    getLang: getLang,
  };
})();

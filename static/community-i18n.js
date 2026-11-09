/* Community and Marketplace share one language preference and server-error vocabulary. */
(() => {
  "use strict";
  function language(user) {
    if (user?.language) return user.language;
    try {
      const saved = JSON.parse(
        localStorage.getItem("sentryloot-region-v1") || "null",
      );
      if (saved?.language) return saved.language;
    } catch {}
    try {
      return localStorage.getItem("bozor-language") || "en";
    } catch {
      return "en";
    }
  }
  function translate(value, language = "en") {
    const source = String(value ?? ""),
      legacy = window.BOZOR_COPY?.[source],
      english = legacy?.[1] || source;
    if (language === "en") return english;
    const copy = window.CommunityCopy?.[language],
      regional = window.SENTRYLOOT_LANGUAGE_DATA?.messages?.[language];
    const exact = copy?.[english] || regional?.[english] || regional?.[source];
    if (exact) return exact;
    if (legacy && language === "uz") return source;
    if (legacy && language === "ru") return legacy[0] || english;
    const range = english.match(/^Use between (\d+) and (\d+) characters\.$/);
    if (range) {
      const template =
        copy?.["Use between {minimum} and {maximum} characters."];
      if (template)
        return template
          .replace("{minimum}", range[1])
          .replace("{maximum}", range[2]);
    }
    return english;
  }
  window.CommunityI18n = Object.freeze({ language, translate });
})();

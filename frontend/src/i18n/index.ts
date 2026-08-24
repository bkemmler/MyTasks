import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import de from "./de.json";
import en from "./en.json";

i18n
  // Reihenfolge: gespeicherte Cookie-Auswahl → Browsersprache; Auswahl
  // wird automatisch im Cookie `mytasks_lang` persistiert.
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      de: { translation: de },
      en: { translation: en },
    },
    supportedLngs: ["de", "en"],
    fallbackLng: "en",
    detection: {
      order: ["cookie", "navigator"],
      lookupCookie: "mytasks_lang",
      caches: ["cookie"],
      cookieOptions: { path: "/", sameSite: "lax", expires: new Date(Date.now() + 365 * 864e5) },
    },
    interpolation: { escapeValue: false },
  });

export default i18n;

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { de, enUS } from "date-fns/locale";
import type { Locale } from "date-fns";
import { api } from "./api";

const LOCALE_MAP: Record<string, string> = {
  de: "de-DE",
  en: "en-US",
};

export function useI18n() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language?.startsWith("de") ? "de" : "en";

  const dateLocale = lang === "de" ? de : enUS;

  // Sprachwechsel: Cookie (i18next macht das) + Profil-Sync, damit
  // E-Mails im Scheduler in derselben Sprache verschickt werden.
  const setLanguage = useCallback(
    (lng: "de" | "en") => {
      if (lng !== i18n.language) {
        i18n.changeLanguage(lng);
        api("/auth/me", {
          method: "PATCH",
          body: JSON.stringify({ locale: LOCALE_MAP[lng] }),
        }).catch(() => {
          // ohne Login (Login-Seite) schlägt PATCH fehl — Cookie reicht
        });
      }
    },
    [i18n],
  );

  return { t, i18n, lang, dateLocale: dateLocale as Locale, setLanguage };
}

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "./locales/en/translation.json";
import kn from "./locales/kn/translation.json";
import hi from "./locales/hi/translation.json";
import ta from "./locales/ta/translation.json";
import te from "./locales/te/translation.json";
import ml from "./locales/ml/translation.json";
import mr from "./locales/mr/translation.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", nativeName: "English" },
  { code: "kn", nativeName: "ಕನ್ನಡ" },
  { code: "hi", nativeName: "हिन्दी" },
  { code: "ta", nativeName: "தமிழ்" },
  { code: "te", nativeName: "తెలుగు" },
  { code: "ml", nativeName: "മലയാളം" },
  { code: "mr", nativeName: "मराठी" },
];

const SUPPORTED_CODES = SUPPORTED_LANGUAGES.map((l) => l.code);
export const STORAGE_KEY = "carbontrack_language";

// Custom detector so we control persistence/key/fallback ourselves,
// while still supporting browser-language auto-detection on first visit.
const storageDetector = {
  name: "carbontrackStorage",
  lookup() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED_CODES.includes(stored)) return stored;
    } catch {
      // localStorage unavailable (e.g. private mode) — fall through
    }
    return undefined;
  },
  cacheUserLanguage(lng) {
    try {
      if (SUPPORTED_CODES.includes(lng)) {
        localStorage.setItem(STORAGE_KEY, lng);
      }
    } catch {
      // ignore persistence failures
    }
  },
};

const languageDetector = new LanguageDetector();
languageDetector.addDetector(storageDetector);

i18n
  .use(languageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      kn: { translation: kn },
      hi: { translation: hi },
      ta: { translation: ta },
      te: { translation: te },
      ml: { translation: ml },
      mr: { translation: mr },
    },
    supportedLngs: SUPPORTED_CODES,
    fallbackLng: "en", // Restriction 2: missing key or unsupported language -> English
    nonExplicitSupportedLngs: true,
    detection: {
      order: ["carbontrackStorage", "navigator"],
      caches: ["carbontrackStorage"],
    },
    interpolation: { escapeValue: false },
    returnEmptyString: false,
    // fallbackLng above already makes i18next fall back to English text
    // for any key missing in the active language, so the user never sees
    // a raw "namespace.key" string (Restriction 2).
  });

export function setLanguage(code) {
  const safeCode = SUPPORTED_CODES.includes(code) ? code : "en";
  i18n.changeLanguage(safeCode);
  try {
    localStorage.setItem(STORAGE_KEY, safeCode);
  } catch {
    // ignore
  }
}

export default i18n;

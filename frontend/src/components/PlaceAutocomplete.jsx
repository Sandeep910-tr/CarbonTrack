import { useEffect, useRef, useState } from "react";
import { LocateFixed, MapPin, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "../lib/api";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 250;

/**
 * Address input with a live "type ahead" suggestions dropdown, backed by
 * the bundled India state/district/village directory (backend
 * /external/places/suggest -> geo_search.py) instead of Google Places
 * Autocomplete - no per-keystroke billed API call, and it still works if
 * the Places key isn't configured.
 *
 * It's still a fully-controlled text field: the driver can type any
 * address by hand exactly as before, and typed text is only ever resolved
 * to coordinates later in the parent's submit handler (NewTrip.jsx ->
 * fetchRoutes). Picking a suggestion just fills the field with a
 * complete "Village, District, State" string so that later geocoding
 * step has an unambiguous address to work with.
 */
export default function PlaceAutocomplete({
  label,
  placeholder,
  value,
  onChange,
  showCurrentLocation = false,
  onUseCurrentLocation,
  locating = false,
  disabled = false,
}) {
  const { t } = useTranslation();
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const containerRef = useRef(null);
  const debounceRef = useRef(null);
  const requestSeqRef = useRef(0);
  const skipNextFetchRef = useRef(false);

  // Close the dropdown on outside click.
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    return () => clearTimeout(debounceRef.current);
  }, []);

  function fetchSuggestions(query) {
    const seq = ++requestSeqRef.current;
    setLoading(true);
    api
      .get("/external/places/suggest", { params: { q: query, limit: 8 } })
      .then((res) => {
        if (seq !== requestSeqRef.current) return; // a newer keystroke already superseded this
        setSuggestions(res.data?.results || []);
        setOpen(true);
        setActiveIndex(-1);
      })
      .catch(() => {
        if (seq !== requestSeqRef.current) return;
        setSuggestions([]);
      })
      .finally(() => {
        if (seq === requestSeqRef.current) setLoading(false);
      });
  }

  function handleInputChange(text) {
    onChange?.(text);

    if (skipNextFetchRef.current) {
      // The text was just set by clicking a suggestion, not typed -
      // don't immediately reopen the dropdown for the very string we
      // just filled in.
      skipNextFetchRef.current = false;
      setOpen(false);
      return;
    }

    clearTimeout(debounceRef.current);
    const trimmed = text.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      requestSeqRef.current++; // invalidate any in-flight request
      setSuggestions([]);
      setLoading(false);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => fetchSuggestions(trimmed), DEBOUNCE_MS);
  }

  function selectSuggestion(suggestion) {
    skipNextFetchRef.current = true;
    onChange?.(suggestion.display);
    setSuggestions([]);
    setOpen(false);
    setActiveIndex(-1);
  }

  function handleKeyDown(e) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      if (activeIndex >= 0 && activeIndex < suggestions.length) {
        e.preventDefault();
        selectSuggestion(suggestions[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  // Bolds the part of the suggestion that matches what was typed, the way
  // map-app search suggestions usually do.
  function renderHighlighted(name, query) {
    const idx = name.toLowerCase().indexOf(query.trim().toLowerCase());
    if (idx === -1 || !query.trim()) return name;
    return (
      <>
        {name.slice(0, idx)}
        <span className="font-semibold text-ink">{name.slice(idx, idx + query.trim().length)}</span>
        {name.slice(idx + query.trim().length)}
      </>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      {label && (
        <div className="mb-1.5 flex items-center justify-between">
          <label className="text-xs font-medium uppercase tracking-wide text-ink-dim">{label}</label>
          {showCurrentLocation && (
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onUseCurrentLocation?.();
              }}
              disabled={locating}
              className="flex items-center gap-1 text-xs font-medium text-amber hover:underline disabled:opacity-50"
            >
              <LocateFixed size={12} /> {locating ? t("placeAutocomplete.locating") : t("placeAutocomplete.useCurrentLocation")}
            </button>
          )}
        </div>
      )}

      <div className="relative">
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          value={value}
          placeholder={placeholder || "Type the full address"}
          disabled={disabled}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 pr-9 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-amber/50 focus:bg-white/[0.05] disabled:opacity-50"
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint">
          {loading ? (
            <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/20 border-t-amber" />
          ) : (
            <Search size={14} />
          )}
        </span>
      </div>

      {open && suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1.5 max-h-64 w-full overflow-y-auto rounded-xl border border-white/10 bg-[#1a1712] shadow-xl"
        >
          {suggestions.map((s, i) => (
            <li key={`${s.display}-${i}`} role="option" aria-selected={i === activeIndex}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()} // keep focus so onChange/onBlur ordering stays predictable
                onClick={() => selectSuggestion(s)}
                onMouseEnter={() => setActiveIndex(i)}
                className={`flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left text-sm transition-colors ${
                  i === activeIndex ? "bg-white/[0.06]" : ""
                }`}
              >
                <MapPin size={14} className="mt-0.5 shrink-0 text-ink-faint" />
                <span className="min-w-0">
                  <span className="block truncate text-ink-dim">
                    {renderHighlighted(s.name, value)}
                  </span>
                  <span className="block truncate text-xs text-ink-faint">
                    {s.level === "state" ? "State" : s.level === "district" ? s.state : `${s.district}, ${s.state}`}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

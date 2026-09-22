let loadPromise = null;

/** Loads the Google Maps JS API once and caches the promise so multiple
 * components can call this without injecting the script tag twice.
 *
 * IMPORTANT: the script is loaded with `loading=async`, which is Google's
 * current recommended pattern — but that means the bootstrap script loading
 * (script.onload firing) only guarantees `google.maps` exists as a stub
 * namespace, NOT that `google.maps.Map`/`Marker`/`geometry` are actually
 * populated yet (those load in the background afterwards). Resolving this
 * promise right on script.onload — as this used to do — causes an
 * intermittent "google.maps.Map is not a constructor" error: it works when
 * the background load happens to finish in time and fails when it doesn't.
 * The fix is to explicitly `importLibrary(...)` each library this app
 * actually uses and await all of them before resolving, per Google's
 * "Dynamic Library Import" docs:
 * https://developers.google.com/maps/documentation/javascript/load-maps-js-api#dynamic-library-import
 *
 * The fast-path check below deliberately verifies geometry (not just Map):
 * on a flaky connection, one caller's load can finish with Map/Marker ready
 * but geometry still not attached. If the fast path only checked Map, a
 * second caller (e.g. a different map on the same page) would short-circuit
 * straight past the geometry check and crash later with "Cannot read
 * properties of undefined (reading 'encoding')" the first time it calls
 * geometry.encoding.decodePath. Checking all three here means that can never
 * happen — a caller either gets a fully-ready `google`, or a rejected
 * promise it can handle the same way as any other load failure.
 */
function isFullyLoaded() {
  return !!(
    window.google?.maps?.Map &&
    window.google.maps.geometry?.encoding &&
    window.google.maps.geometry?.spherical &&
    window.google.maps.places?.Autocomplete
  );
}

export function loadGoogleMaps(apiKey) {
  if (isFullyLoaded()) return Promise.resolve(window.google);
  if (loadPromise) return loadPromise;

  loadPromise = (async () => {
    try {
      // Only inject the <script> tag once — if google.maps.importLibrary
      // already exists (e.g. Map loaded but geometry didn't), just retry
      // importLibrary against the existing bootstrap instead of loading the
      // script a second time.
      if (!window.google?.maps?.importLibrary) {
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&language=en&region=IN&loading=async`;
          script.async = true;
          script.onload = resolve;
          script.onerror = () => { script.remove(); reject(new Error("Google Maps script failed to load")); };
          document.head.appendChild(script);
        });
      }

      // Every library this app actually references client-side:
      //   "maps"     -> google.maps.Map, InfoWindow, etc.
      //   "marker"   -> google.maps.Marker (legacy, still supported)
      //   "geometry" -> google.maps.geometry.spherical / .encoding
      //   "places"   -> google.maps.places.Autocomplete (pickup/destination
      //                 selection - this is what pins the driver's pickup to
      //                 the exact place they chose, instead of relying on
      //                 the backend geocoding whatever free text they typed).
      await Promise.all([
        window.google.maps.importLibrary("maps"),
        window.google.maps.importLibrary("marker"),
        window.google.maps.importLibrary("geometry"),
        window.google.maps.importLibrary("places"),
      ]);

      if (!isFullyLoaded()) {
        throw new Error("Google Maps geometry library did not finish loading");
      }
      return window.google;
    } catch (err) {
      loadPromise = null; // let the next call retry from scratch instead of replaying this failure forever
      throw err;
    }
  })();

  return loadPromise;
}

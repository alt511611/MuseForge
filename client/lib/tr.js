/**
 * Translate with a fallback that actually fires.
 *
 * `t()` returns the KEY itself when a string is missing from every dictionary,
 * so the natural-looking `t("form_lipsync_toggle") || "Dudak senkronu"` never
 * reaches its fallback: the key is a non-empty string, so `||` keeps it and the
 * user is shown the raw identifier. That is not theoretical — the location-lock
 * and lip-sync controls shipped with exactly that guard and rendered
 * "form_lipsync_toggle" as their label until the strings were added.
 *
 * Comparing against the key is the only way to tell a missing string from a
 * real one, so every fallback in the app goes through here.
 *
 *   tr(t, "result_take_n", `take ${n}`, { n })
 *
 * `vars` is forwarded to t() for {placeholder} interpolation; the fallback is
 * expected to have its values already interpolated by the caller (it is a
 * literal in the calling component, where those values are in scope).
 */
export function tr(t, key, fallback, vars) {
  const value = vars ? t(key, vars) : t(key);
  return value === key ? fallback : value;
}

export default tr;

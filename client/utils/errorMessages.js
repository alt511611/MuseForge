const ERROR_MAP = [
  { match: /timeout|timed out|time.?out/i, msg: "The request timed out. Servers may be busy — please try again." },
  { match: /muapi_key|api.?key|not configured|503/i, msg: "The server is not fully configured yet. Please contact support." },
  { match: /quota|rate.?limit|429/i, msg: "API rate limit reached. Wait a minute and try again." },
  { match: /cancelled/i, msg: "Video generation was cancelled." },
  { match: /network|fetch|connection/i, msg: "Network connection lost. Check your internet and try again." },
  { match: /401|unauthorized|sign in|authentication required/i, msg: "Please sign in to continue." },
  { match: /403|forbidden/i, msg: "You do not have permission for this action." },
  { match: /404|not found/i, msg: "Job not found. Refresh the page and try again." },
  { match: /402|insufficient credits/i, msg: "CREDITS_EXHAUSTED" },
  // Keep upstream provider names out of the UI. This sits last so the
  // specific cases above (cancelled, rate limit, timeout) still win.
  { match: /muapi|fal\.?ai|anthropic|claude/i, msg: "The video service is temporarily unavailable. Please try again." },
];

// Belt-and-braces: even an unmatched error must not surface a provider name
// when it reaches the user through the raw-text fallthrough below.
const PROVIDER_NAMES = /\b(muapi|fal\.?ai|anthropic|claude|kling|flux)\b/gi;

export function friendlyError(raw) {
  if (!raw) return "An unexpected error occurred.";
  for (const { match, msg } of ERROR_MAP) {
    if (match.test(raw)) return msg;
  }
  const scrubbed = raw.replace(PROVIDER_NAMES, "the render service");
  return scrubbed.length > 120 ? scrubbed.slice(0, 120) + "…" : scrubbed;
}

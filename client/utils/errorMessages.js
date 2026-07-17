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
];

export function friendlyError(raw) {
  if (!raw) return "An unexpected error occurred.";
  for (const { match, msg } of ERROR_MAP) {
    if (match.test(raw)) return msg;
  }
  const trimmed = raw.length > 120 ? raw.slice(0, 120) + "…" : raw;
  return trimmed;
}

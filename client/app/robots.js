import { SITE_URL } from "../lib/seo";
import { LOCALE_CODES, DEFAULT_LOCALE } from "../lib/i18n/routing";

/* Private or thin routes. Each one exists under every locale prefix too
   (/tr/dashboard, /ja/dashboard, ...), so the list is expanded accordingly —
   a bare "Disallow: /dashboard" would leave 19 crawlable duplicates. */
const PRIVATE_PATHS = ["/admin", "/dashboard", "/generate", "/auth", "/api", "/login"];

/**
 * The crawlers that read this site for a language model, named explicitly.
 *
 * WHY NAME THEM AT ALL, when `User-Agent: *` already allows everything. Two
 * reasons, and neither is that it changes what these bots may fetch today:
 *
 *   1. Intent. Allowing AI crawlers is a decision this product has made — the
 *      site ships /llms.txt and a Markdown edition of every page specifically
 *      for them. Leaving that to the fallback rule makes it look accidental,
 *      and the next person to tighten `*` for an unrelated reason would take
 *      it away without knowing there was anything to take.
 *
 *   2. Google splits the two. Googlebot crawls for Search; Google-Extended is
 *      a separate token that controls use in Gemini and AI Overviews and is
 *      NOT covered by Googlebot's own permissions. A site that wants to appear
 *      in AI Overviews has to say so under that name or not at all.
 *
 * THE FOOTGUN THIS AVOIDS. A named group REPLACES the `*` group for that bot
 * rather than adding to it — robots.txt has no inheritance. So a well-meant
 * `User-agent: GPTBot / Allow: /` on its own does not merely restate the
 * default: it drops every Disallow above it and opens /dashboard, /admin and
 * /generate to that one crawler. Every group below is therefore built from the
 * same `disallow` list, not hand-written.
 */
const AI_CRAWLERS = [
  "GPTBot",            // OpenAI, training
  "OAI-SearchBot",     // OpenAI, ChatGPT search results
  "ChatGPT-User",      // OpenAI, a user-initiated fetch of a link
  "ClaudeBot",         // Anthropic, training
  "Claude-User",       // Anthropic, a user-initiated fetch
  "Claude-SearchBot",  // Anthropic, search indexing
  "PerplexityBot",     // Perplexity, indexing
  "Perplexity-User",   // Perplexity, a user-initiated fetch
  "Google-Extended",   // Google, Gemini and AI Overviews (separate from Googlebot)
  "Applebot-Extended", // Apple, Apple Intelligence
  "Bingbot",           // Microsoft, which also feeds Copilot
  "DuckAssistBot",     // DuckDuckGo
  "cohere-ai",         // Cohere
  "Meta-ExternalAgent",// Meta
];

export default function robots() {
  const disallow = PRIVATE_PATHS.flatMap((p) => [
    p,
    ...LOCALE_CODES.filter((c) => c !== DEFAULT_LOCALE).map((c) => `/${c}${p}`),
  ]);

  return {
    rules: [
      { userAgent: "*", allow: "/", disallow },
      /* Same permissions as everyone else, said out loud. Built from the same
         `disallow` so a new private route cannot be added to the list above
         and quietly stay open to fourteen AI crawlers. */
      ...AI_CRAWLERS.map((userAgent) => ({ userAgent, allow: "/", disallow })),
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    // Yandex's Host directive takes a bare hostname, not a full URL.
    host: new URL(SITE_URL).host,
  };
}

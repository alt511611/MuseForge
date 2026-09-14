import en from "./en";
import tr from "./tr";

/**
 * Article metadata. Locale-independent facts only — anything a reader sees in
 * their own language lives in the per-locale body files beside this one.
 *
 * `published` is the date the piece went live and never moves; `updated` is
 * what dateModified reports and is the one to bump on a substantive edit. The
 * sitemap does not read either — it reads the last commit that touched these
 * files, which is harder to forget.
 */
export default {
  slug: "ai-video-character-consistency",
  category: "guide",
  published: "2026-09-14",
  updated: "2026-09-14",
  tags: ["character consistency", "AI video", "reference image", "continuity"],
  related: ["text-to-video-prompt-guide", "how-to-make-an-ai-short-film"],
  locales: { en, tr },
};

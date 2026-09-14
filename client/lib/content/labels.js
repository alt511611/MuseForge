/**
 * The chrome strings an article page renders around the body.
 *
 * SERVER ONLY — it reaches the dictionary through lib/i18n/index, which pulls
 * all twenty languages. Article pages are server components, so the labels are
 * resolved here and handed down as plain props; no client component ever
 * imports this file (see the warning at the top of lib/i18n/index.js).
 */

import { t } from "../i18n/index";

export function articleLabels(locale) {
  return {
    tldr: t(locale, "blog_tldr"),
    contents: t(locale, "blog_contents"),
    related: t(locale, "blog_related"),
    read_more: t(locale, "blog_read_more"),
    all_articles: t(locale, "blog_all_articles"),
    minutes: t(locale, "blog_minutes"),
    published: t(locale, "blog_published"),
    updated: t(locale, "blog_updated"),
    categories: {
      guide: t(locale, "blog_cat_guide"),
      playbook: t(locale, "blog_cat_playbook"),
      comparison: t(locale, "blog_cat_comparison"),
    },
  };
}

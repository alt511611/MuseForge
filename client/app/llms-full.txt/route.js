import { SITE_URL } from "../../lib/seo";
import { ARTICLES, articlePath, loadArticle } from "../../lib/content";
import { DEFAULT_LOCALE } from "../../lib/i18n/routing";
import { articleToMarkdown } from "../../lib/content/markdown";
import { articleLabels } from "../../lib/content/labels";

/**
 * /llms-full.txt — every English guide, in full, as one Markdown document.
 *
 * The companion to /llms.txt: that file is an index, this is the corpus. An
 * assistant that has decided the guides are relevant can take all of them in
 * one fetch instead of five, which is the difference between being cited and
 * being too expensive to read.
 *
 * Same blocks as the rendered pages — see lib/content/markdown.js on why that
 * identity matters.
 */

export const dynamic = "force-static";

export function GET() {
  const parts = [
    "# MuseForge — Guides",
    "",
    "> Practical guides to AI filmmaking: character consistency, prompting,",
    "> shot design, and shipping a series. Complete text of every English",
    `> article published at ${SITE_URL}/blog.`,
    "",
    "---",
    "",
  ];

  for (const meta of ARTICLES) {
    const article = loadArticle(meta.slug, DEFAULT_LOCALE);
    if (!article) continue;
    parts.push(
      articleToMarkdown(article, `${SITE_URL}${articlePath(meta.slug)}`, articleLabels(DEFAULT_LOCALE)),
      "---",
      ""
    );
  }

  return new Response(parts.join("\n"), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}

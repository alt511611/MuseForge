/**
 * The inline markup an article body is allowed to use.
 *
 * Deliberately four constructs and no parser library. Article prose needs
 * emphasis, code spans and links; everything larger than a sentence is a block
 * (see ./blocks.js), so there is nothing here for a Markdown engine to do that
 * a regex cannot. The alternative was a 40 KB dependency to render `**bold**`.
 *
 *   **strong**     emphasis
 *   *em*           light emphasis
 *   `code`         inline code
 *   [text](/href)  link — site-relative hrefs are localized by the caller
 *
 * Returns React nodes, never a dangerouslySetInnerHTML string: article text is
 * authored in this repo, but rendering it as HTML would make the next author
 * who pastes a quote from a user into a post a stored-XSS bug.
 */

import Link from "next/link";
import { withLocale } from "../i18n/routing";

/* One pass, alternation ordered longest-first so `**a**` never matches the
   single-asterisk arm. The capture groups are read positionally below. */
const TOKEN =
  /\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/g;

function isExternal(href) {
  return /^(https?:|mailto:|#)/.test(href);
}

/**
 * @param {string} text   the raw authored string
 * @param {string} locale so site-relative links stay inside the reader's language
 * @returns {Array<string|JSX.Element>}
 */
export function inline(text, locale) {
  if (typeof text !== "string" || !text) return text ?? null;

  const out = [];
  let cursor = 0;
  let key = 0;
  TOKEN.lastIndex = 0;

  for (let m = TOKEN.exec(text); m; m = TOKEN.exec(text)) {
    if (m.index > cursor) out.push(text.slice(cursor, m.index));
    const [, strong, em, code, linkText, href] = m;

    if (strong !== undefined) {
      out.push(<strong key={key++} className="font-semibold text-ink">{strong}</strong>);
    } else if (em !== undefined) {
      out.push(<em key={key++}>{em}</em>);
    } else if (code !== undefined) {
      out.push(
        <code
          key={key++}
          className="px-1.5 py-0.5 rounded text-[0.85em]"
          style={{ backgroundColor: "var(--mf-panel-2)", color: "var(--mf-violet-soft)" }}
        >
          {code}
        </code>
      );
    } else if (isExternal(href)) {
      /* rel="noopener" on every outbound link: an article is the one page type
         that routinely cites somewhere else. */
      out.push(
        <a
          key={key++}
          href={href}
          target={href.startsWith("#") ? undefined : "_blank"}
          rel={href.startsWith("#") ? undefined : "noopener noreferrer"}
          className="underline underline-offset-2 hover:text-violet-soft transition-colors"
          style={{ color: "var(--mf-violet-soft)" }}
        >
          {linkText}
        </a>
      );
    } else {
      out.push(
        <Link
          key={key++}
          href={withLocale(href, locale)}
          className="underline underline-offset-2 hover:text-violet-soft transition-colors"
          style={{ color: "var(--mf-violet-soft)" }}
        >
          {linkText}
        </Link>
      );
    }
    cursor = m.index + m[0].length;
  }

  if (cursor < text.length) out.push(text.slice(cursor));
  return out.length === 1 ? out[0] : out;
}

/** The same text with every construct stripped — for JSON-LD, which wants plain prose. */
export function plain(text) {
  if (typeof text !== "string") return "";
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();
}

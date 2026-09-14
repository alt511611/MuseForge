/**
 * Blocks -> Markdown.
 *
 * The same article, serialised for a reader that is not a browser. Answer
 * engines and the assistants people paste URLs into do far better with plain
 * Markdown than with the rendered page: no navigation, no cookie banner, no
 * class names between the question and its answer, and the heading structure
 * survives intact so a model can quote one section rather than the whole file.
 *
 * Derived from the same blocks the page renders, so the plain-text edition can
 * never say something the HTML does not — which is the line between publishing
 * a machine-readable copy and cloaking.
 */

import { plain } from "./inline";

/* Inline markup is already Markdown for bold, italics, code and links, so the
   only thing to do is leave it alone. plain() is used where a construct would
   be noise rather than emphasis -- table cells and definition terms. */
const keep = (s) => String(s ?? "").trim();

/**
 * @param {Array} blocks
 * @param {{ tldr?: string, note?: string }} [labels] chrome words that are part
 *   of the prose and therefore belong in the article's language. The front
 *   matter keys in articleToMarkdown stay English on purpose -- those are field
 *   names a parser reads, not sentences a reader does.
 */
export function blocksToMarkdown(blocks = [], labels = {}) {
  const out = [];

  for (const b of blocks) {
    switch (b.t) {
      case "tldr":
        out.push(`**${labels.tldr || "In short"}:**\n` + b.items.map((i) => `- ${keep(i)}`).join("\n"));
        break;
      case "h2":
        out.push(`## ${keep(b.text)}`);
        break;
      case "h3":
        out.push(`### ${keep(b.text)}`);
        break;
      case "p":
        out.push(keep(b.text));
        break;
      case "ul":
        out.push(b.items.map((i) => `- ${keep(i)}`).join("\n"));
        break;
      case "ol":
        out.push(b.items.map((i, n) => `${n + 1}. ${keep(i)}`).join("\n"));
        break;
      case "keyfacts":
        out.push(b.items.map(({ term, value }) => `- **${plain(term)}:** ${keep(value)}`).join("\n"));
        break;
      case "steps":
        out.push(
          `### ${plain(b.name)}\n\n` +
            b.items.map((s, n) => `${n + 1}. **${plain(s.name)}** — ${keep(s.text)}`).join("\n")
        );
        break;
      case "faq":
        /* Question as a heading, answer as the paragraph under it: the shape a
           model looks for when it is trying to answer that exact question. */
        out.push(b.items.map(({ q, a }) => `### ${plain(q)}\n\n${keep(a)}`).join("\n\n"));
        break;
      case "table": {
        const head = b.head.map(plain);
        const rows = b.rows.map((r) => `| ${r.map(plain).join(" | ")} |`);
        out.push([`| ${head.join(" | ")} |`, `|${head.map(() => " --- ").join("|")}|`, ...rows].join("\n"));
        break;
      }
      case "callout":
        out.push(`> **${plain(b.title || labels.note || "Note")}** — ${keep(b.text)}`);
        break;
      case "quote":
        out.push(`> ${keep(b.text)}${b.cite ? `\n>\n> — ${plain(b.cite)}` : ""}`);
        break;
      /* `cta` is a button. It carries no information a reader needs and every
         one of them would read as an advertisement inserted mid-article. */
      case "cta":
      default:
        break;
    }
  }

  return out.join("\n\n");
}

/** One article as a standalone Markdown document, front matter included. */
export function articleToMarkdown(article, url, labels = {}) {
  const head = [
    `# ${article.title}`,
    "",
    `> ${article.description}`,
    "",
    `Source: ${url}  `,
    `Published: ${article.published}${
      article.updated && article.updated !== article.published ? ` · Updated: ${article.updated}` : ""
    }  `,
    `Language: ${article.locale}`,
  ].join("\n");

  return `${head}\n\n${blocksToMarkdown(article.blocks, labels)}\n`;
}

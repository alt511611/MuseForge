import { mdResponse, mdStaticParams } from "../../../lib/content/mdRoute";

/**
 * /md/<locale> — the home page as Markdown.
 *
 * Sits beside /md/<locale>/blog/<slug>, which is more specific and therefore
 * still wins for article URLs.
 */
export const dynamic = "force-static";

export function generateStaticParams() {
  return mdStaticParams("home");
}

export function GET(_request, { params: { locale } }) {
  return mdResponse("home", locale);
}

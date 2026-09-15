import { mdResponse, mdStaticParams } from "../../../../lib/content/mdRoute";

/** /md/<locale>/pricing — the plan ladder as Markdown. */
export const dynamic = "force-static";

export function generateStaticParams() {
  return mdStaticParams("pricing");
}

export function GET(_request, { params: { locale } }) {
  return mdResponse("pricing", locale);
}

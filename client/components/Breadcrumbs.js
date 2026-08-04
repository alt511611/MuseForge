import Link from "next/link";
import { ChevronRight } from "lucide-react";

/**
 * Visible breadcrumb trail. Server component on purpose — it renders in the
 * initial HTML next to the BreadcrumbList JSON-LD it mirrors, which is what
 * makes the schema eligible for a breadcrumb rich result.
 *
 * @param {{ trail: { name: string, path: string }[] }} props
 *   The last entry is the current page and is rendered as plain text.
 */
export default function Breadcrumbs({ trail }) {
  if (!trail?.length) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className="max-w-5xl mx-auto px-6 pt-6"
      style={{ color: "var(--mf-ink-4)" }}
    >
      <ol className="flex flex-wrap items-center gap-1.5 text-xs">
        {trail.map(({ name, path }, i) => {
          const isCurrent = i === trail.length - 1;
          return (
            <li key={path} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight size={12} aria-hidden="true" />}
              {isCurrent ? (
                <span aria-current="page" style={{ color: "var(--mf-ink-3)" }}>
                  {name}
                </span>
              ) : (
                <Link href={path} className="hover:text-violet-soft transition-colors">
                  {name}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

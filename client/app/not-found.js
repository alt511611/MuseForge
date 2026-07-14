import Link from "next/link";
import { Film, ArrowLeft } from "lucide-react";

export const metadata = {
  title: "404 — Page Not Found",
};

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center px-6" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="text-center max-w-md">
        <div className="text-[120px] font-black leading-none mb-4 gradient-text select-none" aria-hidden="true">
          404
        </div>

        <h1 className="text-2xl font-bold mb-3" style={{ color: "#e2e8f0" }}>
          Page Not Found
        </h1>
        <p className="text-sm mb-8" style={{ color: "#64748b" }}>
          The page you&apos;re looking for may have moved, been deleted, or never existed.
          Head back to the homepage and try again.
        </p>

        <div className="flex flex-col sm:flex-row justify-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold transition-all"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
          >
            <Film size={16} />
            Back to Home
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-medium transition-all"
            style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
          >
            <ArrowLeft size={14} />
            Pricing
          </Link>
        </div>
      </div>
    </main>
  );
}

"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw } from "lucide-react";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    console.error("[MuseForge GlobalError]", error);
  }, [error]);

  return (
    <main className="min-h-screen flex items-center justify-center px-6" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="text-center max-w-md">
        <div
          className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-6"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)" }}
        >
          <AlertTriangle size={30} style={{ color: "#ef4444" }} />
        </div>

        <h1 className="text-2xl font-black mb-3 gradient-text">Something went wrong</h1>
        <p className="text-sm mb-2" style={{ color: "#94a3b8" }}>
          {error?.message || "An unexpected error occurred."}
        </p>
        <p className="text-xs mb-8" style={{ color: "#475569" }}>
          If the problem persists, please contact our support team.
        </p>

        <div className="flex justify-center gap-3 flex-wrap">
          <button
            onClick={reset}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
          >
            <RotateCcw size={14} />
            Try Again
          </button>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all"
            style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
          >
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}

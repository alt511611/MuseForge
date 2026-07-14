"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Film, Lock, Loader2, CheckCircle2 } from "lucide-react";
import { useAuth } from "../../../contexts/AuthContext";
import { useLanguage } from "../../../contexts/LanguageContext";

export default function ResetPasswordPage() {
  const router = useRouter();
  const { user, loading, updatePassword } = useAuth();
  const { t } = useLanguage();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  const isReady = !loading;
  const hasSession = !!user;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    setBusy(true);
    try {
      const { error: err } = await updatePassword(password);
      if (err) { setError(err.message); }
      else { setDone(true); setTimeout(() => router.replace("/"), 2500); }
    } finally { setBusy(false); }
  };

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>
            <Film size={28} color="#fff" />
          </div>
          <h1 className="text-3xl font-black tracking-tight gradient-text">MuseForge</h1>
          <p className="text-sm mt-1" style={{ color: "#64748b" }}>{t("reset_page_sub")}</p>
        </div>

        <div className="glass rounded-2xl p-8">
          {done ? (
            <div className="flex flex-col items-center py-4 text-center">
              <CheckCircle2 size={48} className="mb-4" style={{ color: "#22c55e" }} />
              <h2 className="text-xl font-bold mb-2" style={{ color: "#e2e8f0" }}>{t("reset_success_title")}</h2>
              <p className="text-sm" style={{ color: "#64748b" }}>{t("reset_success_desc")}</p>
            </div>
          ) : !hasSession ? (
            <div className="text-center py-4">
              <h2 className="text-lg font-bold mb-3" style={{ color: "#e2e8f0" }}>{t("reset_invalid_title")}</h2>
              <p className="text-sm mb-5" style={{ color: "#64748b" }}>{t("reset_invalid_desc")}</p>
              <a href="/login"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
                style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
                {t("reset_invalid_btn")}
              </a>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold mb-6 text-center" style={{ color: "#e2e8f0" }}>
                {t("reset_title")}
              </h2>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-xs font-medium block mb-1.5" style={{ color: "#94a3b8" }}>
                    {t("reset_new_pw")}
                  </label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                    <input
                      type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                      placeholder="At least 8 characters" required minLength={8}
                      className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm focus:outline-none"
                      style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium block mb-1.5" style={{ color: "#94a3b8" }}>
                    {t("reset_confirm_pw")}
                  </label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                    <input
                      type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                      placeholder="••••••••" required minLength={8}
                      className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm focus:outline-none"
                      style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
                    />
                  </div>
                </div>

                {error && (
                  <div className="text-xs px-3 py-2 rounded-lg" style={{ backgroundColor: "rgba(239,68,68,0.1)", color: "#fca5a5" }}>
                    {error}
                  </div>
                )}

                <button
                  type="submit" disabled={busy}
                  className="w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff", opacity: busy ? 0.7 : 1 }}
                >
                  {busy ? <Loader2 size={16} className="animate-spin" /> : null}
                  {t("reset_submit")}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

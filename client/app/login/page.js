"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../contexts/AuthContext";
import { useLanguage } from "../../contexts/LanguageContext";
import { Film, Mail, Lock, Loader2, Chrome } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/";
  const { user, loading, signInWithEmail, signUpWithEmail, signInWithGoogle, resetPasswordForEmail } = useAuth();
  const { t } = useLanguage();

  const [mode, setMode] = useState("login"); // "login" | "signup" | "forgot"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace(next);
  }, [user, loading, router, next]);

  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setError(null);
    setInfo(null);

    if (mode !== "forgot" && password.length < 6) {
      setError(t("login_password_min"));
      return;
    }

    setBusy(true);
    try {
      if (mode === "forgot") {
        const { error: err } = await resetPasswordForEmail(email);
        if (err) {
          setError(err.message || t("login_error_generic"));
        } else {
          setInfo(t("login_reset_sent"));
          setMode("login");
        }
        return;
      }

      if (mode === "login") {
        const { error: err } = await signInWithEmail(email, password);
        if (err) {
          setError(err.message || t("login_error_generic"));
        } else {
          router.replace(next);
        }
        return;
      }

      // signup
      const { data, error: err } = await signUpWithEmail(email, password);
      if (err) {
        setError(err.message || t("login_error_generic"));
        return;
      }
      // Email confirmation pending: user object exists but no session yet
      if (data?.user && !data?.session) {
        setInfo(t("login_registered"));
        setMode("login");
        setAcceptedTerms(false);
        return;
      }
      if (data?.session) {
        setInfo(t("login_registered"));
        router.replace(next);
        return;
      }
      // Unexpected empty response — still guide the user
      setInfo(t("login_registered"));
      setMode("login");
    } catch (exc) {
      setError(exc?.message || t("login_error_generic"));
    } finally {
      setBusy(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setBusy(true);
    const { error: err } = await signInWithGoogle();
    if (err) { setError(err.message); setBusy(false); }
  };

  const switchMode = (newMode) => {
    setMode(newMode);
    setError(null);
    setInfo(null);
    setAcceptedTerms(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }

  const modeTitle = mode === "login" ? t("login_title_login") : mode === "signup" ? t("login_title_signup") : t("login_title_forgot");

  return (
    <main className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>
            <Film size={28} color="#fff" />
          </div>
          <h1 className="text-3xl font-black tracking-tight gradient-text">MuseForge</h1>
          <p className="text-sm mt-1" style={{ color: "#64748b" }}>{t("login_tagline")}</p>
        </div>

        <div className="glass rounded-2xl p-8">
          <h2 className="text-xl font-semibold mb-6 text-center" style={{ color: "#e2e8f0" }}>
            {modeTitle}
          </h2>

          {mode !== "forgot" && (
            <>
              <button
                onClick={handleGoogle}
                disabled={busy}
                className="w-full flex items-center justify-center gap-3 py-3 rounded-xl text-sm font-medium mb-4 transition-all"
                style={{ backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#e2e8f0" }}
              >
                <Chrome size={18} />
                {t("login_google")}
              </button>
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-1 h-px" style={{ backgroundColor: "#22223a" }} />
                <span className="text-xs" style={{ color: "#475569" }}>{t("login_or")}</span>
                <div className="flex-1 h-px" style={{ backgroundColor: "#22223a" }} />
              </div>
            </>
          )}

          <form onSubmit={handleEmailAuth} className="space-y-4">
            <div>
              <label className="text-xs font-medium block mb-1.5" style={{ color: "#94a3b8" }}>
                {t("login_email")}
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                <input
                  type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com" required
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm focus:outline-none"
                  style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
                />
              </div>
            </div>

            {mode !== "forgot" && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium" style={{ color: "#94a3b8" }}>{t("login_password")}</label>
                  {mode === "login" && (
                    <button type="button" onClick={() => switchMode("forgot")}
                      className="text-xs underline" style={{ color: "#a78bfa" }}>
                      {t("login_forgot")}
                    </button>
                  )}
                </div>
                <div className="relative">
                  <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                  <input
                    type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••" required minLength={6}
                    className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm focus:outline-none"
                    style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
                  />
                </div>
              </div>
            )}

            {mode === "forgot" && (
              <p className="text-xs" style={{ color: "#64748b" }}>{t("login_forgot_desc")}</p>
            )}

            {mode === "signup" && (
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                  className="mt-0.5 rounded"
                  style={{ accentColor: "#7c3aed" }}
                />
                <span className="text-xs leading-relaxed" style={{ color: "#94a3b8" }}>
                  {t("login_accept_prefix")}{" "}
                  <a href="/legal/terms" target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "#a78bfa" }}>
                    {t("login_accept_terms")}
                  </a>
                  {" "}{t("login_accept_and")}{" "}
                  <a href="/legal/privacy" target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "#a78bfa" }}>
                    {t("login_accept_privacy")}
                  </a>
                </span>
              </label>
            )}

            {error && (
              <div className="text-xs px-3 py-2 rounded-lg" style={{ backgroundColor: "rgba(239,68,68,0.1)", color: "#fca5a5" }}>
                {error}
              </div>
            )}
            {info && (
              <div className="text-xs px-3 py-2 rounded-lg" style={{ backgroundColor: "rgba(34,197,94,0.1)", color: "#86efac" }}>
                {info}
              </div>
            )}

            <button
              type="submit"
              disabled={busy || (mode === "signup" && !acceptedTerms)}
              className="w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
              style={{
                background: "linear-gradient(135deg,#7c3aed,#6d28d9)",
                color: "#fff",
                opacity: busy || (mode === "signup" && !acceptedTerms) ? 0.5 : 1,
              }}
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : null}
              {mode === "login" ? t("login_submit_login") : mode === "signup" ? t("login_submit_signup") : t("login_submit_forgot")}
            </button>
          </form>

          <p className="text-center text-xs mt-5" style={{ color: "#64748b" }}>
            {mode === "forgot" ? (
              <button onClick={() => switchMode("login")} className="underline" style={{ color: "#a78bfa" }}>
                {t("login_back")}
              </button>
            ) : (
              <>
                {mode === "login" ? t("login_no_account") : t("login_have_account")}{" "}
                <button onClick={() => switchMode(mode === "login" ? "signup" : "login")}
                  className="underline" style={{ color: "#a78bfa" }}>
                  {mode === "login" ? t("login_signup_link") : t("login_signin_link")}
                </button>
              </>
            )}
          </p>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}

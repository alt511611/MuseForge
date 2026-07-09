"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../contexts/AuthContext";
import { Film, Mail, Lock, Loader2, Chrome } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/";
  const { user, loading, signInWithEmail, signUpWithEmail, signInWithGoogle } = useAuth();

  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    setBusy(true);
    try {
      const { error: err } =
        mode === "login"
          ? await signInWithEmail(email, password)
          : await signUpWithEmail(email, password);

      if (err) {
        setError(err.message);
      } else if (mode === "signup") {
        setInfo("Kayıt başarılı! E-postanızı doğrulayın, ardından giriş yapın.");
        setMode("login");
      } else {
        router.replace(next);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setBusy(true);
    const { error: err } = await signInWithGoogle();
    if (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>
            <Film size={28} color="#fff" />
          </div>
          <h1 className="text-3xl font-black tracking-tight gradient-text">MuseForge</h1>
          <p className="text-sm mt-1" style={{ color: "#64748b" }}>Agentic AI Video Studio</p>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-8">
          <h2 className="text-xl font-semibold mb-6 text-center" style={{ color: "#e2e8f0" }}>
            {mode === "login" ? "Giriş Yap" : "Hesap Oluştur"}
          </h2>

          {/* Google */}
          <button
            onClick={handleGoogle}
            disabled={busy}
            className="w-full flex items-center justify-center gap-3 py-3 rounded-xl text-sm font-medium mb-4 transition-all"
            style={{ backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#e2e8f0" }}
          >
            <Chrome size={18} />
            Google ile {mode === "login" ? "giriş yap" : "kaydol"}
          </button>

          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px" style={{ backgroundColor: "#22223a" }} />
            <span className="text-xs" style={{ color: "#475569" }}>veya</span>
            <div className="flex-1 h-px" style={{ backgroundColor: "#22223a" }} />
          </div>

          {/* Email form */}
          <form onSubmit={handleEmailAuth} className="space-y-4">
            <div>
              <label className="text-xs font-medium block mb-1.5" style={{ color: "#94a3b8" }}>
                E-posta
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="sen@example.com"
                  required
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm focus:outline-none"
                  style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
                />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium block mb-1.5" style={{ color: "#94a3b8" }}>
                Şifre
              </label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "#475569" }} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={6}
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
            {info && (
              <div className="text-xs px-3 py-2 rounded-lg" style={{ backgroundColor: "rgba(34,197,94,0.1)", color: "#86efac" }}>
                {info}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff", opacity: busy ? 0.7 : 1 }}
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : null}
              {mode === "login" ? "Giriş Yap" : "Hesap Oluştur"}
            </button>
          </form>

          <p className="text-center text-xs mt-5" style={{ color: "#64748b" }}>
            {mode === "login" ? "Hesabın yok mu?" : "Zaten hesabın var mı?"}{" "}
            <button
              onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); setInfo(null); }}
              className="underline"
              style={{ color: "#a78bfa" }}
            >
              {mode === "login" ? "Kaydol" : "Giriş yap"}
            </button>
          </p>
        </div>
      </div>
    </main>
  );
}

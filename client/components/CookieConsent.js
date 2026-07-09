"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Cookie, X } from "lucide-react";

const STORAGE_KEY = "museforge_cookie_consent";

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) setVisible(true);
  }, []);

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, "accepted");
    setVisible(false);
  };

  const reject = () => {
    localStorage.setItem(STORAGE_KEY, "rejected");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      className="fixed bottom-4 left-4 right-4 md:left-auto md:right-6 md:max-w-md z-50 animate-slide-up"
      role="dialog"
      aria-label="Çerez bildirimi"
    >
      <div
        className="glass rounded-2xl p-5 shadow-2xl"
        style={{ border: "1px solid rgba(124,58,237,0.3)" }}
      >
        <div className="flex items-start gap-3">
          <div
            className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center mt-0.5"
            style={{ backgroundColor: "rgba(124,58,237,0.15)" }}
          >
            <Cookie size={18} style={{ color: "#a78bfa" }} />
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold mb-1" style={{ color: "#e2e8f0" }}>
              Çerezler Hakkında
            </p>
            <p className="text-xs leading-relaxed mb-3" style={{ color: "#64748b" }}>
              Oturum yönetimi için zorunlu çerezler kullanıyoruz. Analitik çerezlere onay vererek
              hizmetimizi geliştirmemize yardımcı olabilirsiniz.{" "}
              <Link href="/legal/privacy" className="underline" style={{ color: "#a78bfa" }}>
                Gizlilik Politikası
              </Link>
            </p>

            <div className="flex gap-2">
              <button
                onClick={accept}
                className="flex-1 py-2 rounded-xl text-xs font-semibold transition-all"
                style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
              >
                Kabul Et
              </button>
              <button
                onClick={reject}
                className="flex-1 py-2 rounded-xl text-xs font-medium transition-all"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#64748b" }}
              >
                Reddet
              </button>
            </div>
          </div>

          <button
            onClick={reject}
            className="flex-shrink-0 p-1 rounded-lg transition-colors hover:bg-white/5"
            style={{ color: "#475569" }}
            aria-label="Kapat"
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

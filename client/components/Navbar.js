"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Film, LogOut, Shield, ChevronDown, User, LayoutDashboard, Globe, Building2, Users, Clapperboard, BookOpen, AlertTriangle } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { createClient } from "../lib/supabase";
import { isLowCredits } from "../lib/credits";

function LanguageSelector() {
  const { locale, setLocale, LOCALES, LOCALE_CODES, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const current = LOCALES[locale] ?? LOCALES.en;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all"
        style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
        aria-label={t("nav_select_language")}
        title={t("nav_language")}
      >
        <Globe size={13} style={{ color: "#7c3aed" }} />
        <span className="hidden sm:block font-medium">{current.flag} {locale.toUpperCase()}</span>
        <ChevronDown size={11} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in overflow-y-auto"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a", maxHeight: "320px" }}
        >
          {LOCALE_CODES.map((code) => {
            const meta = LOCALES[code];
            const active = code === locale;
            return (
              <button
                key={code}
                onClick={() => { setLocale(code); setOpen(false); }}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-left transition-colors hover:bg-white/5"
                style={{ color: active ? "#a78bfa" : "#94a3b8", backgroundColor: active ? "rgba(124,58,237,0.08)" : "transparent" }}
              >
                <span className="text-base leading-none">{meta.flag}</span>
                <span>{meta.nativeName}</span>
                {active && <span className="ml-auto text-purple-400">✓</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SolutionsDropdown() {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const LINKS = [
    { icon: Building2,   key: "sol_agencies",   href: "/solutions/agencies" },
    { icon: Users,       key: "sol_creators",   href: "/solutions/creators" },
    { icon: Clapperboard,key: "sol_filmmakers", href: "/solutions/filmmakers" },
    { icon: BookOpen,    key: "sol_education",  href: "/solutions/education" },
  ];

  return (
    <div className="relative hidden sm:block" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-sm transition-colors hover:text-purple-400"
        style={{ color: "#64748b" }}
      >
        {t("nav_solutions")}
        <ChevronDown size={13} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
      </button>
      {open && (
        <div
          className="absolute left-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a" }}
        >
          {LINKS.map(({ icon: Icon, key, href }) => (
            <Link key={href} href={href} onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors hover:bg-white/5"
              style={{ color: "#94a3b8" }}>
              <Icon size={14} style={{ color: "#7c3aed" }} />
              {t(key)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Navbar() {
  const { user, isAdmin, signOut, loading } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [lowCredits, setLowCredits] = useState(false);
  const [creditCount, setCreditCount] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!user) {
      setLowCredits(false);
      setCreditCount(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const supabase = createClient();
        if (!supabase) return;
        const { data } = await supabase
          .from("profiles")
          .select("plan, credits")
          .eq("id", user.id)
          .single();
        if (!cancelled && data) {
          setCreditCount(data.credits);
          setLowCredits(isLowCredits(data.credits, data.plan));
        }
      } catch {
        /* ignore */
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const avatarLetter = user?.email?.[0]?.toUpperCase() || "?";

  return (
    <nav
      className="sticky top-0 z-50 flex items-center justify-between px-6 py-3 transition-all duration-300"
      style={{
        backgroundColor: scrolled ? "rgba(10,10,15,0.95)" : "rgba(10,10,15,0.85)",
        backdropFilter: scrolled ? "blur(20px)" : "blur(12px)",
        borderBottom: "1px solid #12121a",
        boxShadow: scrolled ? "0 4px 24px rgba(0,0,0,0.4)" : "none",
      }}
    >
      <Link href="/" className="flex items-center gap-2">
        <Film size={20} style={{ color: "#7c3aed" }} />
        <span className="font-black tracking-tight gradient-text text-lg">MuseForge</span>
      </Link>

      <div className="flex items-center gap-3">
        <SolutionsDropdown />

        <Link href="/pricing"
          className="hidden sm:inline-flex items-center text-sm transition-colors hover:text-purple-400"
          style={{ color: "#64748b" }}>
          {t("nav_pricing")}
        </Link>

        {user && lowCredits && (
          <Link
            href="/dashboard"
            className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium"
            style={{ backgroundColor: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.35)", color: "#fbbf24" }}
            title={t("credits_low_banner", { n: creditCount ?? 0 })}
          >
            <AlertTriangle size={11} />
            {creditCount ?? "—"}
          </Link>
        )}

        <LanguageSelector />

        {!loading && (
          <div>
            {user ? (
              <div className="relative" ref={ref}>
                <button
                  onClick={() => setOpen(!open)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm transition-all relative"
                  style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
                >
                  {lowCredits && (
                    <span
                      className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: "#fbbf24", boxShadow: "0 0 0 2px #0a0a0f" }}
                      aria-hidden
                    />
                  )}
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
                  >
                    {avatarLetter}
                  </div>
                  <span className="hidden sm:block max-w-[120px] truncate">{user.email}</span>
                  <ChevronDown size={14} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
                </button>

                {open && (
                  <div
                    className="absolute right-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in"
                    style={{ backgroundColor: "#12121a", border: "1px solid #22223a" }}
                  >
                    <div className="px-4 py-2 border-b" style={{ borderColor: "#22223a" }}>
                      <p className="text-xs font-medium truncate" style={{ color: "#e2e8f0" }}>{user.email}</p>
                      {isAdmin && (
                        <p className="text-[10px] mt-0.5" style={{ color: "#a78bfa" }}>{t("nav_admin_badge")}</p>
                      )}
                      {lowCredits && (
                        <Link href="/pricing" onClick={() => setOpen(false)}
                          className="block text-[10px] mt-1" style={{ color: "#fbbf24" }}>
                          {t("credits_low_banner", { n: creditCount ?? 0 })}
                        </Link>
                      )}
                    </div>
                    <Link
                      href="/dashboard"
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "#94a3b8" }}
                    >
                      <LayoutDashboard size={14} />
                      {t("nav_dashboard")}
                    </Link>
                    {isAdmin && (
                      <Link
                        href="/admin"
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                        style={{ color: "#a78bfa" }}
                      >
                        <Shield size={14} />
                        {t("nav_admin")}
                      </Link>
                    )}
                    <button
                      onClick={handleSignOut}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "#f87171" }}
                    >
                      <LogOut size={14} />
                      {t("nav_signout")}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Link
                href="/login"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all"
                style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
              >
                <User size={14} />
                {t("nav_signin")}
              </Link>
            )}
          </div>
        )}
      </div>
    </nav>
  );
}

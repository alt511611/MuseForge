"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Film, LogOut, Shield, ChevronDown, User, LayoutDashboard, Globe, Building2, Users, Clapperboard, BookOpen, AlertTriangle, Menu, X } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
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
        style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
        aria-label={t("nav_select_language")}
        title={t("nav_language")}
      >
        <Globe size={13} style={{ color: "var(--mf-violet)" }} />
        <span className="hidden sm:block font-medium">{current.flag} {locale.toUpperCase()}</span>
        <ChevronDown size={11} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in overflow-y-auto"
          style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", maxHeight: "320px" }}
        >
          {LOCALE_CODES.map((code) => {
            const meta = LOCALES[code];
            const active = code === locale;
            return (
              <button
                key={code}
                onClick={() => { setLocale(code); setOpen(false); }}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-left transition-colors hover:bg-white/5"
                style={{ color: active ? "var(--mf-violet-soft)" : "var(--mf-ink-2)", backgroundColor: active ? "rgba(139,92,246,0.08)" : "transparent" }}
              >
                <span className="text-base leading-none">{meta.flag}</span>
                <span>{meta.nativeName}</span>
                {active && <span className="ml-auto" style={{ color: "var(--mf-violet-soft)" }}>✓</span>}
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
        className="flex items-center gap-1 text-sm transition-colors hover:text-violet-soft"
        style={{ color: "var(--mf-ink-3)" }}
      >
        {t("nav_solutions")}
        <ChevronDown size={13} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
      </button>
      {open && (
        <div
          className="absolute left-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in"
          style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)" }}
        >
          {LINKS.map(({ icon: Icon, key, href }) => (
            <Link key={href} href={href} onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors hover:bg-white/5"
              style={{ color: "var(--mf-ink-2)" }}>
              <Icon size={14} style={{ color: "var(--mf-violet)" }} />
              {t(key)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Navbar() {
  const { user, profile, isAdmin, signOut, loading } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
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

  // Profile comes from AuthContext, which fetches the row once per user --
  // this component used to run its own identical query alongside IdeaForm's.
  useEffect(() => {
    if (!user || !profile) {
      setLowCredits(false);
      setCreditCount(null);
      return;
    }
    setCreditCount(profile.credits);
    setLowCredits(isLowCredits(profile.credits, profile.plan));
  }, [user, profile]);

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const avatarLetter = user?.email?.[0]?.toUpperCase() || "?";

  return (
    <nav
      className="sticky top-0 z-50 transition-all duration-300"
      style={{
        backgroundColor: scrolled ? "rgba(7,7,11,0.95)" : "rgba(7,7,11,0.82)",
        backdropFilter: scrolled ? "blur(20px)" : "blur(12px)",
        borderBottom: "1px solid var(--mf-line)",
        boxShadow: scrolled ? "0 4px 24px rgba(0,0,0,0.4)" : "none",
      }}
    >
      <div className="flex items-center justify-between px-4 sm:px-6 py-3">
      <Link href="/" className="flex items-center gap-2 min-w-0">
        <Film size={20} style={{ color: "var(--mf-violet)" }} className="flex-shrink-0" />
        <span className="font-black tracking-tight gradient-text text-lg truncate">MuseForge</span>
      </Link>

      <div className="flex items-center gap-2 sm:gap-3">
        <SolutionsDropdown />

        <Link href="/pricing"
          className="hidden sm:inline-flex items-center text-sm transition-colors hover:text-violet-soft"
          style={{ color: "var(--mf-ink-3)" }}>
          {t("nav_pricing")}
        </Link>

        {user && lowCredits && (
          <Link
            href="/dashboard"
            className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium"
            style={{ backgroundColor: "rgba(232,182,76,0.12)", border: "1px solid rgba(232,182,76,0.35)", color: "var(--mf-gold)" }}
            title={t("credits_low_banner", { n: creditCount ?? 0 })}
          >
            <AlertTriangle size={11} />
            {creditCount ?? "—"}
          </Link>
        )}

        <LanguageSelector />

        <button
          type="button"
          className="sm:hidden p-2 rounded-lg"
          style={{ color: "var(--mf-ink-2)", backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)" }}
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
          onClick={() => setMobileOpen((v) => !v)}
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        {!loading && (
          <div className="hidden sm:block">
            {user ? (
              <div className="relative" ref={ref}>
                <button
                  onClick={() => setOpen(!open)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm transition-all relative"
                  style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
                >
                  {lowCredits && (
                    <span
                      className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: "var(--mf-gold)", boxShadow: "0 0 0 2px var(--mf-stage)" }}
                      aria-hidden
                    />
                  )}
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
                  >
                    {avatarLetter}
                  </div>
                  <span className="hidden sm:block max-w-[120px] truncate">{user.email}</span>
                  <ChevronDown size={14} className={open ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
                </button>

                {open && (
                  <div
                    className="absolute right-0 mt-2 w-52 rounded-xl py-1 z-50 animate-fade-in"
                    style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)" }}
                  >
                    <div className="px-4 py-2 border-b" style={{ borderColor: "var(--mf-line-strong)" }}>
                      <p className="text-xs font-medium truncate" style={{ color: "var(--mf-ink)" }}>{user.email}</p>
                      {isAdmin && (
                        <p className="text-[10px] mt-0.5" style={{ color: "var(--mf-violet-soft)" }}>{t("nav_admin_badge")}</p>
                      )}
                      {lowCredits && (
                        <Link href="/pricing" onClick={() => setOpen(false)}
                          className="block text-[10px] mt-1" style={{ color: "var(--mf-gold)" }}>
                          {t("credits_low_banner", { n: creditCount ?? 0 })}
                        </Link>
                      )}
                    </div>
                    <Link
                      href="/dashboard"
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "var(--mf-ink-2)" }}
                    >
                      <LayoutDashboard size={14} />
                      {t("nav_dashboard")}
                    </Link>
                    {isAdmin && (
                      <Link
                        href="/admin"
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                        style={{ color: "var(--mf-violet-soft)" }}
                      >
                        <Shield size={14} />
                        {t("nav_admin")}
                      </Link>
                    )}
                    <button
                      onClick={handleSignOut}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "var(--mf-err)" }}
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
                style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
              >
                <User size={14} />
                {t("nav_signin")}
              </Link>
            )}
          </div>
        )}
      </div>
      </div>

      {mobileOpen && (
        <div className="sm:hidden px-4 pb-4 space-y-1 border-t" style={{ borderColor: "var(--mf-line)" }}>
          <Link href="/pricing" onClick={() => setMobileOpen(false)}
            className="block px-3 py-2.5 rounded-lg text-sm" style={{ color: "var(--mf-ink-2)" }}>
            {t("nav_pricing")}
          </Link>
          <p className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide" style={{ color: "var(--mf-ink-4)" }}>{t("nav_solutions")}</p>
          {[
            { href: "/solutions/agencies", key: "sol_agencies" },
            { href: "/solutions/creators", key: "sol_creators" },
            { href: "/solutions/filmmakers", key: "sol_filmmakers" },
            { href: "/solutions/education", key: "sol_education" },
          ].map(({ href, key }) => (
            <Link key={href} href={href} onClick={() => setMobileOpen(false)}
              className="block px-3 py-2 rounded-lg text-sm" style={{ color: "var(--mf-ink-2)" }}>
              {t(key)}
            </Link>
          ))}
          {user ? (
            <>
              <Link href="/dashboard" onClick={() => setMobileOpen(false)}
                className="block px-3 py-2.5 rounded-lg text-sm" style={{ color: "var(--mf-ink-2)" }}>
                {t("nav_dashboard")}
              </Link>
              {isAdmin && (
                <Link href="/admin" onClick={() => setMobileOpen(false)}
                  className="block px-3 py-2.5 rounded-lg text-sm" style={{ color: "var(--mf-violet-soft)" }}>
                  {t("nav_admin")}
                </Link>
              )}
              {lowCredits && (
                <Link href="/pricing" onClick={() => setMobileOpen(false)}
                  className="block px-3 py-2 text-xs" style={{ color: "var(--mf-gold)" }}>
                  {t("credits_low_banner", { n: creditCount ?? 0 })}
                </Link>
              )}
              <button type="button" onClick={() => { setMobileOpen(false); handleSignOut(); }}
                className="w-full text-left px-3 py-2.5 rounded-lg text-sm" style={{ color: "var(--mf-err)" }}>
                {t("nav_signout")}
              </button>
            </>
          ) : (
            <Link href="/login" onClick={() => setMobileOpen(false)}
              className="block px-3 py-2.5 rounded-lg text-sm font-medium" style={{ color: "var(--mf-violet-soft)" }}>
              {t("nav_signin")}
            </Link>
          )}
        </div>
      )}
    </nav>
  );
}

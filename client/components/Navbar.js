"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Film, LogOut, Shield, ChevronDown, User } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

export default function Navbar() {
  const { user, isAdmin, signOut, loading } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const avatarLetter = user?.email?.[0]?.toUpperCase() || "?";

  return (
    <nav
      className="sticky top-0 z-50 flex items-center justify-between px-6 py-3"
      style={{ backgroundColor: "rgba(10,10,15,0.85)", backdropFilter: "blur(12px)", borderBottom: "1px solid #12121a" }}
    >
      <Link href="/" className="flex items-center gap-2">
        <Film size={20} style={{ color: "#7c3aed" }} />
        <span className="font-black tracking-tight gradient-text text-lg">MuseForge</span>
      </Link>

      {!loading && (
        <div>
          {user ? (
            <div className="relative" ref={ref}>
              <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm transition-all"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
              >
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
                >
                  {avatarLetter}
                </div>
                <span className="hidden sm:block max-w-[140px] truncate">{user.email}</span>
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
                      <p className="text-[10px] mt-0.5" style={{ color: "#a78bfa" }}>Admin</p>
                    )}
                  </div>
                  {isAdmin && (
                    <Link
                      href="/admin"
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "#a78bfa" }}
                    >
                      <Shield size={14} />
                      Admin Paneli
                    </Link>
                  )}
                  <button
                    onClick={handleSignOut}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-white/5"
                    style={{ color: "#94a3b8" }}
                  >
                    <LogOut size={14} />
                    Çıkış Yap
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
            >
              <User size={14} />
              Giriş Yap
            </Link>
          )}
        </div>
      )}
    </nav>
  );
}

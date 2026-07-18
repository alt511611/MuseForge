"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Film, Plus, ExternalLink, AlertCircle, Clock, CheckCircle2, XCircle, Loader2, Video, RefreshCw, CreditCard, Sparkles, X } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useLanguage } from "../../contexts/LanguageContext";
import { createClient } from "../../lib/supabase";
import { isLowCredits } from "../../lib/credits";
import { API_BASE } from "../../lib/apiBase";

const PAGE_SIZE = 12;

function StatusBadge({ status }) {
  const { t } = useLanguage();
  const META = {
    completed: { key: "status_completed", color: "#22c55e", Icon: CheckCircle2 },
    failed:    { key: "status_failed",    color: "#ef4444", Icon: XCircle },
    running:   { key: "status_running",   color: "#60a5fa", Icon: Loader2, pulse: true },
    queued:    { key: "status_queued",    color: "#94a3b8", Icon: Clock },
    cancelled: { key: "status_cancelled", color: "#f59e0b", Icon: XCircle },
  };
  const meta = META[status] || META.queued;
  const { key, color, Icon, pulse } = meta;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ backgroundColor: `${color}18`, color }}>
      <Icon size={11} className={pulse ? "animate-spin" : ""} />
      {t(key)}
    </span>
  );
}

function JobCard({ job }) {
  const { t } = useLanguage();
  const idea = job.idea?.length > 90 ? job.idea.slice(0, 90) + "…" : job.idea;
  const date = job.created_at
    ? new Date(job.created_at).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })
    : "-";
  const videoUrl = job.result?.video_url;
  const isActive = ["queued", "running"].includes(job.status);

  return (
    <div className="glass rounded-2xl p-5 flex flex-col gap-3 hover:border-purple-600/40 transition-all"
      style={{ border: "1px solid rgba(124,58,237,0.1)" }}>
      <div className="flex items-start justify-between gap-2">
        <StatusBadge status={job.status} />
        {job.demo && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: "rgba(251,191,36,0.15)", color: "#fbbf24" }}>
            {t("dash_demo_badge")}
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed flex-1" style={{ color: "#cbd5e1" }}>
        {idea || <span style={{ color: "#475569" }}>—</span>}
      </p>
      <div className="flex items-center justify-between mt-auto pt-2 border-t" style={{ borderColor: "#1a1a26" }}>
        <span className="text-xs" style={{ color: "#475569" }}>{date}</span>
        <div className="flex items-center gap-2">
          {isActive && (
            <Link href={`/generate/${job.id}`}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(96,165,250,0.12)", color: "#60a5fa" }}>
              <Loader2 size={11} className="animate-spin" />
              {t("dash_watch")}
            </Link>
          )}
          {job.status === "completed" && (
            <>
              {videoUrl && (
                <a href={videoUrl} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
                  style={{ backgroundColor: "rgba(34,197,94,0.12)", color: "#22c55e" }}>
                  <Video size={11} />
                  {t("dash_watch")}
                </a>
              )}
              <Link href={`/generate/${job.id}`}
                className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
                style={{ backgroundColor: "#1a1a26", color: "#94a3b8", border: "1px solid #22223a" }}>
                <ExternalLink size={11} />
                {t("dash_detail")}
              </Link>
            </>
          )}
          {job.status === "failed" && (
            <Link href={`/?idea=${encodeURIComponent(job.idea || "")}`}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(239,68,68,0.12)", color: "#fca5a5" }}>
              <RefreshCw size={11} />
              {t("dash_retry")}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="glass rounded-2xl p-5 animate-pulse" style={{ border: "1px solid rgba(124,58,237,0.05)" }}>
      <div className="h-5 w-24 rounded-full mb-3" style={{ backgroundColor: "#1a1a26" }} />
      <div className="h-3 w-full rounded mb-2" style={{ backgroundColor: "#1a1a26" }} />
      <div className="h-3 w-3/4 rounded mb-4" style={{ backgroundColor: "#1a1a26" }} />
      <div className="h-3 w-20 rounded" style={{ backgroundColor: "#1a1a26" }} />
    </div>
  );
}

function BuyCreditsModal({ onClose, getAccessToken }) {
  const { t } = useLanguage();
  const [loading, setLoading] = useState(null);
  const [err, setErr] = useState(null);

  const PACKAGES = [
    { key: "SMALL",  label: t("pricing_credits_small"), price: "$9",  highlight: false },
    { key: "MEDIUM", label: t("pricing_credits_medium"), price: "$19", highlight: true },
    { key: "LARGE",  label: t("pricing_credits_large"), price: "$39", highlight: false },
  ];

  const buy = async (pkg) => {
    setLoading(pkg); setErr(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/buy-credits`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          package: pkg,
          success_url: `${window.location.origin}/dashboard?credits=bought`,
          cancel_url: `${window.location.origin}/dashboard`,
        }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Error"); }
      const { url } = await res.json();
      window.location.href = url;
    } catch (e) { setErr(e.message); setLoading(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md glass rounded-2xl p-7" style={{ border: "1px solid rgba(124,58,237,0.3)" }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold" style={{ color: "#e2e8f0" }}>
            <Sparkles size={16} className="inline mr-2" style={{ color: "#7c3aed" }} />
            {t("dash_buy_credits")}
          </h3>
          <button onClick={onClose} style={{ color: "#64748b" }}><X size={18} /></button>
        </div>
        <p className="text-xs mb-5" style={{ color: "#64748b" }}>No subscription required. Credits never expire.</p>
        <div className="space-y-3">
          {PACKAGES.map((pkg) => (
            <div key={pkg.key}
              className="flex items-center justify-between p-4 rounded-xl"
              style={{
                backgroundColor: pkg.highlight ? "rgba(124,58,237,0.08)" : "#0d0d14",
                border: pkg.highlight ? "1px solid rgba(124,58,237,0.35)" : "1px solid #1a1a26",
              }}>
              <div>
                <p className="text-sm font-bold" style={{ color: "#e2e8f0" }}>{pkg.label}</p>
                <p className="text-xl font-black" style={{ color: pkg.highlight ? "#a78bfa" : "#64748b" }}>{pkg.price}</p>
              </div>
              <button onClick={() => buy(pkg.key)} disabled={!!loading}
                className="px-4 py-2 rounded-xl text-sm font-semibold transition-all"
                style={pkg.highlight
                  ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff", opacity: loading ? 0.7 : 1 }
                  : { backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8", opacity: loading ? 0.7 : 1 }}>
                {loading === pkg.key ? <Loader2 size={14} className="animate-spin inline" /> : t("pricing_credits_buy")}
              </button>
            </div>
          ))}
        </div>
        {err && <p className="text-xs mt-3" style={{ color: "#fca5a5" }}>{err}</p>}
      </div>
    </div>
  );
}

function ManageSubscriptionButton({ getAccessToken }) {
  const { t } = useLanguage();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleClick = async () => {
    setLoading(true); setError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/stripe-portal`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ return_url: window.location.href }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Portal unavailable"); }
      const { url } = await res.json();
      window.location.href = url;
    } catch (err) { setError(err.message); setLoading(false); }
  };

  return (
    <div>
      <button onClick={handleClick} disabled={loading}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all"
        style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8", opacity: loading ? 0.6 : 1 }}>
        {loading ? <Loader2 size={14} className="animate-spin" /> : <CreditCard size={14} />}
        {t("dash_manage_sub")}
      </button>
      {error && <p className="text-xs mt-1" style={{ color: "#fca5a5" }}>{error}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading: authLoading, getAccessToken } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();

  const [jobs, setJobs] = useState([]);
  const [profile, setProfile] = useState(null);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [showBuyModal, setShowBuyModal] = useState(false);
  const [ledger, setLedger] = useState([]);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login?next=/dashboard");
  }, [user, authLoading, router]);

  const fetchJobs = useCallback(async (pageNum = 0) => {
    const supabase = createClient();
    if (!supabase) return;
    setFetching(true); setError(null);
    try {
      const from = pageNum * PAGE_SIZE;
      const to = from + PAGE_SIZE - 1;
      const { data, error: err } = await supabase
        .from("jobs")
        .select("id, idea, status, demo, result, error, created_at, style")
        .order("created_at", { ascending: false })
        .range(from, to + 1);
      if (err) throw err;
      const slice = (data || []).slice(0, PAGE_SIZE);
      setHasMore((data || []).length > PAGE_SIZE);
      if (pageNum === 0) setJobs(slice);
      else setJobs((prev) => [...prev, ...slice]);
    } catch (err) {
      setError(err.message);
    } finally {
      setFetching(false);
    }
  }, []);

  const fetchProfile = useCallback(async () => {
    const supabase = createClient();
    if (!supabase || !user) return;
    const { data } = await supabase.from("profiles").select("plan, credits, role").eq("id", user.id).single();
    if (data) setProfile(data);
  }, [user]);

  const fetchLedger = useCallback(async () => {
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/credits`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setLedger(data.ledger || []);
        if (data.credits !== undefined && profile) {
          setProfile((p) => p ? { ...p, credits: data.credits } : p);
        }
      }
    } catch {}
  }, [getAccessToken, profile]);

  useEffect(() => {
    if (user) { fetchJobs(0); fetchProfile(); }
  }, [user, fetchJobs, fetchProfile]);

  useEffect(() => {
    if (user) fetchLedger();
  }, [user, fetchLedger]);

  const loadMore = () => { const next = page + 1; setPage(next); fetchJobs(next); };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }
  if (!user) return null;

  const LEDGER_COLORS = {
    video_generation: "#ef4444",
    subscription_renewal: "#22c55e",
    credit_purchase: "#a78bfa",
    refund: "#60a5fa",
  };

  const stats = {
    total: jobs.length,
    completed: jobs.filter(j => j.status === "completed").length,
    running: jobs.filter(j => ["running", "queued"].includes(j.status)).length,
    failed: jobs.filter(j => j.status === "failed").length,
  };

  const lowCredits = profile && isLowCredits(profile.credits, profile.plan);

  const PLAN_LABEL_KEYS = { free: "dash_plan_free", creator: "dash_plan_creator", pro: "dash_plan_pro" };

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      {showBuyModal && <BuyCreditsModal onClose={() => setShowBuyModal(false)} getAccessToken={getAccessToken} />}
      <div className="max-w-5xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10">
          <div>
            <h1 className="text-3xl font-black gradient-text">{t("dash_title")}</h1>
            <p className="text-sm mt-1" style={{ color: "#64748b" }}>{user.email}</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <ManageSubscriptionButton getAccessToken={getAccessToken} />
            <Link href="/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              <Plus size={15} />
              {t("dash_new")}
            </Link>
          </div>
        </div>

        {lowCredits && (
          <div
            className="mb-6 px-5 py-4 rounded-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
            style={{ backgroundColor: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.35)" }}
          >
            <p className="text-sm font-medium" style={{ color: "#fbbf24" }}>
              {t("credits_low_banner", { n: profile.credits })}
            </p>
            <button
              type="button"
              onClick={() => setShowBuyModal(true)}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
            >
              <Sparkles size={13} />
              {t("credits_low_buy")}
            </button>
          </div>
        )}

        {/* Profile / plan card */}
        {profile && (
          <div className="glass rounded-2xl p-5 mb-8 flex flex-wrap gap-6 items-center"
            style={{ border: "1px solid rgba(124,58,237,0.15)" }}>
            <div>
              <p className="text-xs mb-0.5" style={{ color: "#64748b" }}>{t("dash_plan")}</p>
              <p className="text-base font-bold" style={{ color: "#a78bfa" }}>
                {t(PLAN_LABEL_KEYS[profile.plan] || "dash_plan_free")}
              </p>
            </div>
            <div>
              <p className="text-xs mb-0.5" style={{ color: "#64748b" }}>{t("dash_credits")}</p>
              <p className="text-base font-bold" style={{ color: "#e2e8f0" }}>{profile.credits ?? "—"}</p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button onClick={() => setShowBuyModal(true)}
                className="text-xs px-3 py-1.5 rounded-xl font-medium inline-flex items-center gap-1.5 transition-all"
                style={{ backgroundColor: "#12121a", border: "1px solid rgba(124,58,237,0.35)", color: "#a78bfa" }}>
                <Sparkles size={11} /> {t("dash_buy_credits")}
              </button>
              {profile.plan === "free" && (
                <Link href="/pricing"
                  className="text-xs px-3 py-1.5 rounded-xl font-medium"
                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
                  {t("dash_upgrade")}
                </Link>
              )}
            </div>
          </div>
        )}

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { key: "dash_total",          value: stats.total,     color: "#a78bfa" },
            { key: "dash_completed_stat", value: stats.completed, color: "#22c55e" },
            { key: "dash_generating_stat",value: stats.running,   color: "#60a5fa" },
            { key: "dash_failed_stat",    value: stats.failed,    color: "#ef4444" },
          ].map(({ key, value, color }) => (
            <div key={key} className="glass rounded-xl p-4 text-center"
              style={{ border: "1px solid rgba(124,58,237,0.08)" }}>
              <p className="text-2xl font-black" style={{ color }}>{value}</p>
              <p className="text-xs mt-0.5" style={{ color: "#64748b" }}>{t(key)}</p>
            </div>
          ))}
        </div>

        {/* Credit ledger */}
        {ledger.length > 0 && (
          <div className="glass rounded-2xl p-5 mb-8" style={{ border: "1px solid rgba(124,58,237,0.08)" }}>
            <p className="text-sm font-semibold mb-4" style={{ color: "#e2e8f0" }}>{t("dash_credit_history")}</p>
            <div className="space-y-2">
              {ledger.slice(0, 8).map((entry, i) => {
                const color = LEDGER_COLORS[entry.reason] || "#64748b";
                const sign = entry.amount > 0 ? "+" : "";
                const date = entry.created_at
                  ? new Date(entry.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                  : "";
                return (
                  <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b last:border-0"
                    style={{ borderColor: "#1a1a26" }}>
                    <span style={{ color: "#94a3b8" }}>{entry.reason?.replace(/_/g, " ")}</span>
                    <div className="flex items-center gap-3">
                      <span style={{ color: "#475569" }}>{date}</span>
                      <span className="font-bold" style={{ color }}>{sign}{entry.amount}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-4 rounded-xl mb-6 text-sm"
            style={{ backgroundColor: "rgba(239,68,68,0.08)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.2)" }}>
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Job grid */}
        {fetching && jobs.length === 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
              style={{ background: "rgba(124,58,237,0.12)", border: "1px solid rgba(124,58,237,0.2)" }}>
              <Film size={28} style={{ color: "#7c3aed" }} />
            </div>
            <h2 className="text-xl font-bold mb-2" style={{ color: "#e2e8f0" }}>{t("dash_empty_title")}</h2>
            <p className="text-sm mb-6" style={{ color: "#475569" }}>{t("dash_empty_desc")}</p>
            <Link href="/"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              <Plus size={15} />
              {t("dash_create")}
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {jobs.map(job => <JobCard key={job.id} job={job} />)}
              {fetching && Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={`sk-${i}`} />)}
            </div>
            {hasMore && !fetching && (
              <div className="text-center mt-8">
                <button onClick={loadMore}
                  className="px-6 py-2.5 rounded-xl text-sm font-medium transition-all"
                  style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
                  {t("dash_load_more")}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

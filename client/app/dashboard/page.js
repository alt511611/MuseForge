"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Film, Plus, ExternalLink, AlertCircle, Clock, CheckCircle2, XCircle, Loader2, Video, RefreshCw, CreditCard } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { createClient } from "../../lib/supabase";

const PAGE_SIZE = 12;

const STATUS_META = {
  completed:  { label: "Tamamlandı", color: "#22c55e", Icon: CheckCircle2 },
  failed:     { label: "Başarısız",  color: "#ef4444", Icon: XCircle },
  running:    { label: "Üretiliyor", color: "#60a5fa", Icon: Loader2,  pulse: true },
  queued:     { label: "Kuyrukta",   color: "#94a3b8", Icon: Clock },
  cancelled:  { label: "İptal",      color: "#f59e0b", Icon: XCircle },
};

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.queued;
  const { label, color, Icon, pulse } = meta;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ backgroundColor: `${color}18`, color }}>
      <Icon size={11} className={pulse ? "animate-spin" : ""} />
      {label}
    </span>
  );
}

function JobCard({ job, apiBase }) {
  const idea = job.idea?.length > 90 ? job.idea.slice(0, 90) + "…" : job.idea;
  const date = job.created_at
    ? new Date(job.created_at).toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" })
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
            Demo
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
              İzle
            </Link>
          )}
          {job.status === "completed" && (
            <>
              {videoUrl && (
                <a href={videoUrl} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
                  style={{ backgroundColor: "rgba(34,197,94,0.12)", color: "#22c55e" }}>
                  <Video size={11} />
                  İzle
                </a>
              )}
              <Link href={`/generate/${job.id}`}
                className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
                style={{ backgroundColor: "#1a1a26", color: "#94a3b8", border: "1px solid #22223a" }}>
                <ExternalLink size={11} />
                Detay
              </Link>
            </>
          )}
          {job.status === "failed" && (
            <Link href={`/?idea=${encodeURIComponent(job.idea || "")}`}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(239,68,68,0.12)", color: "#fca5a5" }}>
              <RefreshCw size={11} />
              Tekrar
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

function ManageSubscriptionButton({ user, getAccessToken }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleClick = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/stripe-portal`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ return_url: window.location.href }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Portal başlatılamadı");
      }
      const { url } = await res.json();
      window.location.href = url;
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div>
      <button onClick={handleClick} disabled={loading}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all"
        style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8", opacity: loading ? 0.6 : 1 }}>
        {loading ? <Loader2 size={14} className="animate-spin" /> : <CreditCard size={14} />}
        Aboneliğimi Yönet
      </button>
      {error && <p className="text-xs mt-1" style={{ color: "#fca5a5" }}>{error}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading: authLoading, getAccessToken } = useAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState([]);
  const [profile, setProfile] = useState(null);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login?next=/dashboard");
  }, [user, authLoading, router]);

  const fetchJobs = useCallback(async (pageNum = 0) => {
    const supabase = createClient();
    if (!supabase) return;

    setFetching(true);
    setError(null);

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
    const { data } = await supabase
      .from("profiles")
      .select("plan, credits, role")
      .eq("id", user.id)
      .single();
    if (data) setProfile(data);
  }, [user]);

  useEffect(() => {
    if (user) {
      fetchJobs(0);
      fetchProfile();
    }
  }, [user, fetchJobs, fetchProfile]);

  const loadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchJobs(nextPage);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }

  if (!user) return null;

  const stats = {
    total: jobs.length,
    completed: jobs.filter(j => j.status === "completed").length,
    running: jobs.filter(j => ["running", "queued"].includes(j.status)).length,
    failed: jobs.filter(j => j.status === "failed").length,
  };

  const PLAN_LABELS = { free: "Ücretsiz", creator: "Creator", pro: "Pro" };

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-5xl mx-auto px-6 py-12">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10">
          <div>
            <h1 className="text-3xl font-black gradient-text">Video Geçmişim</h1>
            <p className="text-sm mt-1" style={{ color: "#64748b" }}>{user.email}</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <ManageSubscriptionButton user={user} getAccessToken={getAccessToken} />
            <Link href="/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              <Plus size={15} />
              Yeni Video
            </Link>
          </div>
        </div>

        {/* Profile / plan card */}
        {profile && (
          <div className="glass rounded-2xl p-5 mb-8 flex flex-wrap gap-6 items-center"
            style={{ border: "1px solid rgba(124,58,237,0.15)" }}>
            <div>
              <p className="text-xs mb-0.5" style={{ color: "#64748b" }}>Plan</p>
              <p className="text-base font-bold" style={{ color: "#a78bfa" }}>
                {PLAN_LABELS[profile.plan] || profile.plan}
              </p>
            </div>
            <div>
              <p className="text-xs mb-0.5" style={{ color: "#64748b" }}>Kalan Kredit</p>
              <p className="text-base font-bold" style={{ color: "#e2e8f0" }}>{profile.credits ?? "—"}</p>
            </div>
            {profile.plan === "free" && (
              <Link href="/pricing"
                className="ml-auto text-xs px-3 py-1.5 rounded-xl font-medium"
                style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
                Planı Yükselt →
              </Link>
            )}
          </div>
        )}

        {/* Stats bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { label: "Toplam",      value: stats.total,     color: "#a78bfa" },
            { label: "Tamamlanan",  value: stats.completed, color: "#22c55e" },
            { label: "Üretiliyor",  value: stats.running,   color: "#60a5fa" },
            { label: "Başarısız",   value: stats.failed,    color: "#ef4444" },
          ].map(({ label, value, color }) => (
            <div key={label} className="glass rounded-xl p-4 text-center"
              style={{ border: "1px solid rgba(124,58,237,0.08)" }}>
              <p className="text-2xl font-black" style={{ color }}>{value}</p>
              <p className="text-xs mt-0.5" style={{ color: "#64748b" }}>{label}</p>
            </div>
          ))}
        </div>

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
            <h2 className="text-xl font-bold mb-2" style={{ color: "#e2e8f0" }}>Henüz video yok</h2>
            <p className="text-sm mb-6" style={{ color: "#475569" }}>İlk videonuzu oluşturarak başlayın.</p>
            <Link href="/"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              <Plus size={15} />
              Video Oluştur
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {jobs.map(job => (
                <JobCard key={job.id} job={job} apiBase={apiBase} />
              ))}
              {fetching && Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={`sk-${i}`} />)}
            </div>

            {hasMore && !fetching && (
              <div className="text-center mt-8">
                <button onClick={loadMore}
                  className="px-6 py-2.5 rounded-xl text-sm font-medium transition-all"
                  style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
                  Daha Fazla Yükle
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

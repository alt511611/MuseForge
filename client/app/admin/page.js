"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart3, Film, CheckCircle2, XCircle, Loader2,
  RefreshCw, Trash2, Eye, ArrowLeft, Activity,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const STATUS_COLOR = {
  completed: "#22c55e",
  failed: "#ef4444",
  running: "#a78bfa",
  queued: "#fbbf24",
  cancelled: "#64748b",
};

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="glass rounded-2xl p-5 flex items-center gap-4">
      <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ backgroundColor: `${color}20` }}>
        <Icon size={22} style={{ color }} />
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color: "#e2e8f0" }}>{value}</p>
        <p className="text-xs" style={{ color: "#64748b" }}>{label}</p>
      </div>
    </div>
  );
}

function JobModal({ job, onClose, onRetry, onDelete }) {
  if (!job) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
    >
      <div
        className="glass rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto animate-fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold" style={{ color: "#e2e8f0" }}>Job #{job.id}</h2>
            <p className="text-xs mt-0.5" style={{ color: "#64748b" }}>{job.created_at?.slice(0, 19).replace("T", " ")} UTC</p>
          </div>
          <span className="text-xs px-2 py-1 rounded-full" style={{ backgroundColor: `${STATUS_COLOR[job.status] || "#94a3b8"}20`, color: STATUS_COLOR[job.status] || "#94a3b8" }}>
            {job.status}
          </span>
        </div>

        <p className="text-sm mb-4 px-3 py-2 rounded-lg" style={{ backgroundColor: "#12121a", color: "#94a3b8" }}>
          &ldquo;{job.idea}&rdquo;
        </p>

        <div className="grid grid-cols-2 gap-2 text-xs mb-4" style={{ color: "#64748b" }}>
          <div>Stil: <span style={{ color: "#94a3b8" }}>{job.style}</span></div>
          <div>Yönetmen: <span style={{ color: "#94a3b8" }}>{job.director_style}</span></div>
          <div>Oran: <span style={{ color: "#94a3b8" }}>{job.aspect_ratio}</span></div>
          <div>Sahneler: <span style={{ color: "#94a3b8" }}>{job.num_scenes}</span></div>
          <div>Kullanıcı: <span style={{ color: "#94a3b8" }}>{job.user_email || "anonim"}</span></div>
          <div>Demo: <span style={{ color: "#94a3b8" }}>{job.demo ? "evet" : "hayır"}</span></div>
        </div>

        {job.error && (
          <div className="text-xs px-3 py-2 rounded-lg mb-4" style={{ backgroundColor: "rgba(239,68,68,0.1)", color: "#fca5a5" }}>
            {job.error}
          </div>
        )}

        {job.events?.length > 0 && (
          <div>
            <p className="text-xs font-medium mb-2" style={{ color: "#64748b" }}>Olay Günlüğü</p>
            <div className="space-y-1 max-h-48 overflow-y-auto font-mono text-xs"
              style={{ backgroundColor: "#0a0a0f", borderRadius: 8, padding: "8px 12px" }}>
              {job.events.map((ev, i) => (
                <div key={i} className="flex gap-2">
                  <span style={{ color: "#475569" }}>{ev.timestamp?.slice(11, 19)}</span>
                  <span style={{ color: "#7c3aed" }}>[{ev.stage}]</span>
                  <span style={{ color: "#94a3b8" }}>{ev.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2 mt-5">
          {job.status !== "running" && (
            <button onClick={() => onRetry(job.id)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all"
              style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa", border: "1px solid rgba(124,58,237,0.3)" }}>
              <RefreshCw size={14} /> Yeniden Dene
            </button>
          )}
          <button onClick={() => onDelete(job.id)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{ backgroundColor: "rgba(239,68,68,0.1)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.3)" }}>
            <Trash2 size={14} /> Sil
          </button>
          <button onClick={onClose}
            className="ml-auto px-4 py-2 rounded-xl text-sm"
            style={{ color: "#64748b" }}>
            Kapat
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { user, isAdmin, loading: authLoading, getAccessToken } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [fetching, setFetching] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const LIMIT = 20;

  useEffect(() => {
    if (!authLoading && (!user || !isAdmin)) router.replace("/");
  }, [user, isAdmin, authLoading, router]);

  const apiFetch = useCallback(async (url, options = {}) => {
    const token = await getAccessToken();
    return fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  }, [getAccessToken]);

  const loadData = useCallback(async () => {
    setFetching(true);
    try {
      const [statsRes, jobsRes] = await Promise.all([
        apiFetch("/api/admin/stats"),
        apiFetch(`/api/admin/jobs?limit=${LIMIT}&offset=${page * LIMIT}`),
      ]);
      if (statsRes.ok) setStats(await statsRes.json());
      if (jobsRes.ok) {
        const d = await jobsRes.json();
        setJobs(d.jobs);
        setTotal(d.total);
      }
    } finally {
      setFetching(false);
    }
  }, [apiFetch, page]);

  useEffect(() => { if (isAdmin) loadData(); }, [isAdmin, loadData]);

  const openJobDetail = async (id) => {
    const res = await apiFetch(`/api/admin/jobs/${id}`);
    if (res.ok) setSelectedJob(await res.json());
  };

  const handleRetry = async (id) => {
    const res = await apiFetch(`/api/admin/jobs/${id}/retry`, { method: "POST" });
    if (res.ok) { setSelectedJob(null); loadData(); }
  };

  const handleDelete = async (id) => {
    if (!confirm("Bu job silinsin mi?")) return;
    const res = await apiFetch(`/api/admin/jobs/${id}`, { method: "DELETE" });
    if (res.ok) { setSelectedJob(null); loadData(); }
  };

  if (authLoading || (!isAdmin && user === null)) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#0a0a0f" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "#7c3aed" }} />
      </div>
    );
  }

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-sm flex items-center gap-1.5 transition-colors hover:text-purple-400" style={{ color: "#64748b" }}>
              <ArrowLeft size={14} /> Ana Sayfa
            </Link>
            <span style={{ color: "#22223a" }}>/</span>
            <h1 className="text-xl font-bold gradient-text">Admin Paneli</h1>
          </div>
          <button onClick={loadData} disabled={fetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
            style={{ color: "#64748b", border: "1px solid #22223a" }}>
            <RefreshCw size={14} className={fetching ? "animate-spin" : ""} />
            Yenile
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard icon={Film} label="Toplam Job" value={stats.total} color="#7c3aed" />
            <StatCard icon={CheckCircle2} label="Tamamlandı" value={stats.completed} color="#22c55e" />
            <StatCard icon={XCircle} label="Başarısız" value={stats.failed} color="#ef4444" />
            <StatCard icon={Activity} label="Çalışıyor" value={stats.running} color="#a78bfa" />
          </div>
        )}

        {/* Jobs table */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid #1a1a26" }}>
            <h2 className="text-sm font-medium flex items-center gap-2" style={{ color: "#a78bfa" }}>
              <BarChart3 size={16} /> Tüm Job'lar
            </h2>
            <span className="text-xs" style={{ color: "#475569" }}>{total} kayıt</span>
          </div>

          {fetching ? (
            <div className="flex justify-center py-12">
              <Loader2 className="animate-spin" size={24} style={{ color: "#7c3aed" }} />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid #1a1a26" }}>
                    {["ID", "Kullanıcı", "Fikir", "Durum", "Tarih", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-medium" style={{ color: "#475569" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id} style={{ borderBottom: "1px solid #12121a" }} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: "#94a3b8" }}>{job.id}</td>
                      <td className="px-4 py-3 text-xs max-w-[140px] truncate" style={{ color: "#64748b" }}>{job.user_email || "anonim"}</td>
                      <td className="px-4 py-3 text-xs max-w-[200px] truncate" style={{ color: "#94a3b8" }}>{job.idea}</td>
                      <td className="px-4 py-3">
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: `${STATUS_COLOR[job.status] || "#94a3b8"}15`, color: STATUS_COLOR[job.status] || "#94a3b8" }}>
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs" style={{ color: "#475569" }}>{job.created_at?.slice(0, 10)}</td>
                      <td className="px-4 py-3">
                        <button onClick={() => openJobDetail(job.id)}
                          className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg transition-all"
                          style={{ backgroundColor: "rgba(124,58,237,0.1)", color: "#a78bfa" }}>
                          <Eye size={12} /> Detay
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-4" style={{ borderTop: "1px solid #1a1a26" }}>
              <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                className="text-xs px-3 py-1.5 rounded-lg transition-all disabled:opacity-40"
                style={{ color: "#94a3b8", border: "1px solid #22223a" }}>
                Önceki
              </button>
              <span className="text-xs" style={{ color: "#475569" }}>{page + 1} / {totalPages}</span>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
                className="text-xs px-3 py-1.5 rounded-lg transition-all disabled:opacity-40"
                style={{ color: "#94a3b8", border: "1px solid #22223a" }}>
                Sonraki
              </button>
            </div>
          )}
        </div>
      </div>

      <JobModal job={selectedJob} onClose={() => setSelectedJob(null)} onRetry={handleRetry} onDelete={handleDelete} />
    </main>
  );
}

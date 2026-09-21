"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "../../../components/LocaleLink";
import {
  Film,
  Plus,
  Sparkles,
  Loader2,
  AlertCircle,
  X,
  Users,
  Lock,
} from "lucide-react";
import { useAuth } from "../../../contexts/AuthContext";
import { useLanguage } from "../../../contexts/LanguageContext";
import { API_BASE } from "../../../lib/apiBase";
import { friendlyError } from "../../../utils/errorMessages";
import { tr } from "../../../lib/tr";

// Kept in sync with IdeaForm.js's single-job option lists — a series locks
// the same production choices for every episode, so the picker offers the
// same values rather than inventing a second vocabulary.
const STYLES = [
  "Cinematic",
  "Noir",
  "Sci-Fi",
  "Fantasy",
  "Horror",
  "Romance",
  "Documentary",
  "Anime",
];

const DIRECTOR_STYLES = [
  { id: "slow_cinematic", label: "Slow Cinematic" },
  { id: "cinematic_balanced", label: "Balanced" },
  { id: "dynamic_action", label: "Dynamic Action" },
  { id: "intimate_closeup", label: "Intimate" },
  { id: "noir_mystery", label: "Noir Mystery" },
  { id: "anime_expressive", label: "Anime" },
];

const ASPECT_RATIOS = ["9:16", "16:9", "1:1"];
const DELIVERY_TIERS = ["1080p", "720p", "1440p", "4k", "480p"];
const PLAN_MAX_SCENES = { free: 8, creator: 16, pro: 24 };

function SkeletonCard() {
  return (
    <div className="mf-card p-5 animate-pulse" style={{ border: "1px solid rgba(139,92,246,0.05)" }}>
      <div className="h-5 w-32 rounded mb-3" style={{ backgroundColor: "var(--mf-panel-2)" }} />
      <div className="h-3 w-full rounded mb-2" style={{ backgroundColor: "var(--mf-panel-2)" }} />
      <div className="h-3 w-3/4 rounded" style={{ backgroundColor: "var(--mf-panel-2)" }} />
    </div>
  );
}

function SeriesCard({ series }) {
  const { t } = useLanguage();
  const portraits = (series.cast || []).filter((c) => c.portrait_url).slice(0, 4);
  return (
    <Link
      href={`/series/${series.id}`}
      className="mf-card mf-card-hover p-5 flex flex-col gap-3"
      style={{ border: "1px solid rgba(139,92,246,0.1)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-bold" style={{ color: "var(--mf-ink)" }}>
          {series.title || "—"}
        </h3>
        <span
          className="text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0"
          style={{ backgroundColor: "rgba(139,92,246,0.12)", color: "var(--mf-violet-soft)" }}
        >
          {tr(t, "series_episodes_count", `${series.episode_count} episodes`, { n: series.episode_count })}
        </span>
      </div>
      <p className="text-sm leading-relaxed flex-1 line-clamp-2" style={{ color: "var(--mf-ink-2)" }}>
        {series.premise || <span style={{ color: "var(--mf-ink-4)" }}>—</span>}
      </p>
      <div className="flex items-center justify-between mt-auto pt-2 border-t" style={{ borderColor: "var(--mf-line)" }}>
        <div className="flex -space-x-2">
          {portraits.length > 0 ? (
            portraits.map((c, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={c.portrait_url}
                alt={c.name}
                className="w-7 h-7 rounded-full object-cover"
                style={{ border: "2px solid var(--mf-panel)" }}
              />
            ))
          ) : (
            <span className="text-xs" style={{ color: "var(--mf-ink-4)" }}>
              {tr(t, "series_bible_no_cast", "Cast not locked yet")}
            </span>
          )}
        </div>
        <span className="text-xs font-medium" style={{ color: "var(--mf-violet-soft)" }}>
          {tr(t, "series_next_episode", `Next: Episode ${series.next_episode}`, { n: series.next_episode })}
        </span>
      </div>
    </Link>
  );
}

function NewSeriesModal({ onClose, onCreated, getAccessToken, plan }) {
  const { t } = useLanguage();
  const [title, setTitle] = useState("");
  const [premise, setPremise] = useState("");
  const [style, setStyle] = useState("Cinematic");
  const [directorStyle, setDirectorStyle] = useState("cinematic_balanced");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [narrativeMode, setNarrativeMode] = useState("micro_drama");
  const [numScenes, setNumScenes] = useState(3);
  const [deliveryTier, setDeliveryTier] = useState("");
  const [libraryCharacters, setLibraryCharacters] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const maxScenes = PLAN_MAX_SCENES[plan] ?? PLAN_MAX_SCENES.free;

  // Same Pro-only saved-character picker IdeaForm.js already has — the shape
  // /api/characters returns matches SeriesCreateRequest.cast[] exactly.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getAccessToken();
        if (!token || cancelled) return;
        const res = await fetch(`${API_BASE}/api/characters`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (!cancelled) setLibraryCharacters(Array.isArray(data.characters) ? data.characters : []);
      } catch {
        /* picker just stays empty */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getAccessToken]);

  const toggleId = (id) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim() || !premise.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const token = await getAccessToken();
      const cast = libraryCharacters
        .filter((c) => selectedIds.includes(c.id))
        .map((c) => ({
          name: c.name,
          static_features: c.static_features,
          portrait_url: c.portrait_url,
          voice_id: c.voice_id || "",
          wardrobe: c.wardrobe || "",
        }));
      const res = await fetch(`${API_BASE}/api/series`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          title: title.trim(),
          premise: premise.trim(),
          style,
          director_style: directorStyle,
          aspect_ratio: aspectRatio,
          narrative_mode: narrativeMode,
          num_scenes: numScenes,
          delivery_tier: deliveryTier,
          cast,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 403) {
          setError("PRO_REQUIRED");
          return;
        }
        throw new Error(typeof data.detail === "string" ? data.detail : "");
      }
      onCreated(data);
    } catch (err) {
      setError(friendlyError(err.message) || tr(t, "series_create_failed", "Could not create the series"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8 overflow-y-auto"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg mf-card p-7 my-auto" style={{ border: "1px solid rgba(139,92,246,0.3)" }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold" style={{ color: "var(--mf-ink)" }}>
            <Sparkles size={16} className="inline mr-2" style={{ color: "var(--mf-violet)" }} />
            {t("series_new")}
          </h3>
          <button onClick={onClose} style={{ color: "var(--mf-ink-3)" }}>
            <X size={18} />
          </button>
        </div>

        {error === "PRO_REQUIRED" ? (
          <div className="text-center py-6">
            <Lock size={28} className="mx-auto mb-3" style={{ color: "var(--mf-gold)" }} />
            <p className="text-sm font-semibold mb-1" style={{ color: "var(--mf-ink)" }}>
              {t("series_pro_required_title")}
            </p>
            <p className="text-xs mb-5" style={{ color: "var(--mf-ink-3)" }}>
              {t("series_pro_required_desc")}
            </p>
            <Link href="/pricing" className="mf-btn-primary inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold">
              {t("series_pro_required_cta")}
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                {t("series_create_title")}
              </label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("series_create_title_ph")}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
              />
            </div>
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                {t("series_create_premise")}
              </label>
              <textarea
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                placeholder={t("series_create_premise_ph")}
                rows={3}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_style")}
                </label>
                <select
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                >
                  {STYLES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_director_style")}
                </label>
                <select
                  value={directorStyle}
                  onChange={(e) => setDirectorStyle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                >
                  {DIRECTOR_STYLES.map((d) => (
                    <option key={d.id} value={d.id}>{d.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_aspect_ratio")}
                </label>
                <select
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                >
                  {ASPECT_RATIOS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_num_scenes")}: {numScenes}
                </label>
                <input
                  type="range"
                  min={2}
                  max={maxScenes}
                  value={numScenes}
                  onChange={(e) => setNumScenes(Number(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_narrative_mode")}
                </label>
                <select
                  value={narrativeMode}
                  onChange={(e) => setNarrativeMode(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                >
                  <option value="micro_drama">{t("series_create_narrative_micro_drama")}</option>
                  <option value="cinematic">{t("series_create_narrative_cinematic")}</option>
                </select>
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>
                  {t("series_create_delivery_tier")}
                </label>
                <select
                  value={deliveryTier}
                  onChange={(e) => setDeliveryTier(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                >
                  <option value="">—</option>
                  {DELIVERY_TIERS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
            </div>

            {libraryCharacters.length > 0 && (
              <div>
                <label className="text-xs mb-1 flex items-center gap-1.5" style={{ color: "var(--mf-ink-3)" }}>
                  <Users size={12} /> {t("series_create_cast")}
                </label>
                <p className="text-[11px] mb-2" style={{ color: "var(--mf-ink-4)" }}>
                  {t("series_create_cast_hint")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {libraryCharacters.map((c) => {
                    const selected = selectedIds.includes(c.id);
                    return (
                      <button
                        type="button"
                        key={c.id}
                        onClick={() => toggleId(c.id)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all"
                        style={{
                          backgroundColor: selected ? "rgba(139,92,246,0.18)" : "var(--mf-panel-2)",
                          border: selected ? "1px solid var(--mf-violet)" : "1px solid var(--mf-line-strong)",
                          color: selected ? "var(--mf-violet-soft)" : "var(--mf-ink-2)",
                        }}
                      >
                        {c.portrait_url && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={c.portrait_url} alt={c.name} className="w-4 h-4 rounded-full object-cover" />
                        )}
                        {c.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {error && error !== "PRO_REQUIRED" && (
              <p className="text-xs" style={{ color: "var(--mf-err-soft)" }}>{error}</p>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={submitting || !title.trim() || !premise.trim()}
                className="mf-btn-primary flex-1 inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold disabled:opacity-50"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                {t("series_create_submit")}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-5 py-2.5 rounded-xl text-sm font-medium"
                style={{ backgroundColor: "var(--mf-panel-2)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
              >
                {t("series_create_cancel")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function SeriesListPage() {
  const { user, loading: authLoading, getAccessToken, profile } = useAuth();
  const { t, localeHref } = useLanguage();
  const router = useRouter();

  const [series, setSeries] = useState([]);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState(null);
  const [showNewModal, setShowNewModal] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace(localeHref("/login?next=/series"));
  }, [user, authLoading, router, localeHref]);

  const fetchSeries = useCallback(async () => {
    setFetching(true);
    setError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("");
      const data = await res.json();
      setSeries(Array.isArray(data.series) ? data.series : []);
    } catch (err) {
      setError(friendlyError(err.message));
    } finally {
      setFetching(false);
    }
  }, [getAccessToken]);

  useEffect(() => {
    if (user) fetchSeries();
  }, [user, fetchSeries]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "var(--mf-stage)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--mf-violet)" }} />
      </div>
    );
  }
  if (!user) return null;

  const isPro = profile?.plan === "pro";

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      {showNewModal && (
        <NewSeriesModal
          getAccessToken={getAccessToken}
          plan={profile?.plan}
          onClose={() => setShowNewModal(false)}
          onCreated={(created) => {
            setShowNewModal(false);
            router.push(localeHref(`/series/${created.id}`));
          }}
        />
      )}
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10">
          <div>
            <h1 className="display text-3xl gradient-text">{t("series_title")}</h1>
          </div>
          <button
            onClick={() => setShowNewModal(true)}
            className="mf-btn-primary inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
          >
            <Plus size={15} />
            {t("series_new")}
          </button>
        </div>

        {error && (
          <div
            className="flex items-center gap-2 p-4 rounded-xl mb-6 text-sm"
            style={{ backgroundColor: "rgba(248,113,113,0.08)", color: "var(--mf-err-soft)", border: "1px solid rgba(248,113,113,0.2)" }}
          >
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {fetching && series.length === 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : series.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
              style={{ background: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.2)" }}
            >
              <Film size={28} style={{ color: "var(--mf-violet)" }} />
            </div>
            <h2 className="text-xl font-bold mb-2" style={{ color: "var(--mf-ink)" }}>
              {t("series_empty_title")}
            </h2>
            <p className="text-sm mb-6 max-w-sm" style={{ color: "var(--mf-ink-4)" }}>
              {t("series_empty_desc")}
            </p>
            {!isPro && (
              <p className="text-xs mb-4" style={{ color: "var(--mf-gold)" }}>
                {t("series_pro_required_desc")}
              </p>
            )}
            <button
              onClick={() => setShowNewModal(true)}
              className="mf-btn-primary inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
            >
              <Plus size={15} />
              {t("series_new")}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {series.map((s) => (
              <SeriesCard key={s.id} series={s} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

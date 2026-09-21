"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "../../../../components/LocaleLink";
import {
  ArrowLeft,
  Sparkles,
  Loader2,
  AlertCircle,
  Trash2,
  CheckCircle2,
  Clock,
  Video,
  ExternalLink,
  MapPin,
  BookOpen,
  HelpCircle,
  ShieldCheck,
  Ban,
} from "lucide-react";
import { useAuth } from "../../../../contexts/AuthContext";
import { useLanguage } from "../../../../contexts/LanguageContext";
import { API_BASE } from "../../../../lib/apiBase";
import { friendlyError } from "../../../../utils/errorMessages";
import { tr } from "../../../../lib/tr";

function EpisodeStatusBadge({ status }) {
  const { t } = useLanguage();
  const META = {
    completed: { key: "series_episode_status_completed", color: "var(--mf-ok)", Icon: CheckCircle2 },
    running: { key: "series_episode_status_running", color: "#60a5fa", Icon: Loader2, pulse: true },
    queued: { key: "series_episode_status_queued", color: "var(--mf-ink-2)", Icon: Clock },
    awaiting_confirmation: { key: "series_episode_status_awaiting_confirmation", color: "var(--mf-gold)", Icon: AlertCircle },
    rejected: { key: "series_episode_status_rejected", color: "var(--mf-err-soft)", Icon: Ban },
  };
  const meta = META[status] || META.queued;
  const { key, color, Icon, pulse } = meta;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ backgroundColor: `${color}18`, color }}
    >
      <Icon size={11} className={pulse ? "animate-spin" : ""} />
      {t(key)}
    </span>
  );
}

function EpisodeRow({ episode, onConfirm, onReject, busy }) {
  const { t } = useLanguage();
  const pending = episode.status === "awaiting_confirmation";
  return (
    <div className="mf-card p-4 flex flex-col gap-2" style={{ border: pending ? "1px solid rgba(232,182,76,0.35)" : "1px solid rgba(139,92,246,0.08)" }}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-bold" style={{ color: "var(--mf-ink)" }}>
          {`#${episode.number}`}
          {episode.title ? ` — ${episode.title}` : ""}
        </span>
        <EpisodeStatusBadge status={episode.status} />
      </div>
      {episode.synopsis && (
        <p className="text-xs leading-relaxed" style={{ color: "var(--mf-ink-2)" }}>
          {episode.synopsis}
        </p>
      )}
      {episode.cliffhanger && (
        <p className="text-xs italic" style={{ color: "var(--mf-gold)" }}>
          {episode.cliffhanger}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 mt-1">
        {episode.job_id && (
          <Link
            href={`/generate/${episode.job_id}`}
            className="inline-flex items-center gap-1 text-xs self-start px-2.5 py-1 rounded-lg"
            style={{ backgroundColor: "var(--mf-panel-2)", color: "var(--mf-violet-soft)", border: "1px solid var(--mf-line-strong)" }}
          >
            {episode.status === "completed" || pending ? <Video size={11} /> : <ExternalLink size={11} />}
            {episode.status === "completed" || pending ? t("dash_watch") : t("dash_detail")}
          </Link>
        )}
        {pending && (
          <>
            <button
              type="button"
              onClick={() => onConfirm(episode.number)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg disabled:opacity-50"
              style={{ backgroundColor: "rgba(52,211,153,0.12)", color: "var(--mf-ok)", border: "1px solid rgba(52,211,153,0.3)" }}
            >
              <ShieldCheck size={11} />
              {t("series_confirm_episode")}
            </button>
            <button
              type="button"
              onClick={() => onReject(episode.number)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg disabled:opacity-50"
              style={{ backgroundColor: "rgba(248,113,113,0.1)", color: "var(--mf-err-soft)", border: "1px solid rgba(248,113,113,0.3)" }}
            >
              <Ban size={11} />
              {t("series_reject_episode")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function SeriesDetailPage() {
  const { id } = useParams();
  const { user, loading: authLoading, getAccessToken, profile } = useAuth();
  const { t, localeHref } = useLanguage();
  const router = useRouter();

  const [series, setSeries] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const [idea, setIdea] = useState("");
  const [userRequirement, setUserRequirement] = useState("");
  const [requireScriptApproval, setRequireScriptApproval] = useState(true);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [dialogueEnabled, setDialogueEnabled] = useState(false);
  const [lipsyncEnabled, setLipsyncEnabled] = useState(false);
  const [ordering, setOrdering] = useState(false);
  const [orderError, setOrderError] = useState(null);
  const [reviewingNumber, setReviewingNumber] = useState(null);
  const [reviewError, setReviewError] = useState(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace(localeHref(`/login?next=/series/${id}`));
  }, [user, authLoading, router, localeHref, id]);

  const fetchSeries = useCallback(async () => {
    setFetching(true);
    setError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series/${id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.status === 404) {
        setNotFound(true);
        return;
      }
      if (!res.ok) throw new Error("");
      setSeries(await res.json());
    } catch (err) {
      setError(friendlyError(err.message));
    } finally {
      setFetching(false);
    }
  }, [id, getAccessToken]);

  useEffect(() => {
    if (user && id) fetchSeries();
  }, [user, id, fetchSeries]);

  const isPro = profile?.plan === "pro";
  const dialogueEligible = isPro && dialogueEnabled;
  const pendingEpisode = (series?.episodes || []).find((e) => e.status === "awaiting_confirmation");

  const handleConfirm = async (number) => {
    if (reviewingNumber) return;
    setReviewingNumber(number);
    setReviewError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series/${id}/episodes/${number}/confirm`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "");
      }
      setSeries(data);
    } catch (err) {
      setReviewError(friendlyError(err.message) || tr(t, "series_confirm_failed", "Could not confirm the episode"));
    } finally {
      setReviewingNumber(null);
    }
  };

  const handleReject = async (number) => {
    if (reviewingNumber) return;
    if (typeof window !== "undefined" && !window.confirm(t("series_reject_confirm"))) return;
    setReviewingNumber(number);
    setReviewError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series/${id}/episodes/${number}/reject`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "");
      }
      setSeries(data);
    } catch (err) {
      setReviewError(friendlyError(err.message) || tr(t, "series_reject_failed", "Could not reject the episode"));
    } finally {
      setReviewingNumber(null);
    }
  };

  const handleOrder = async (e) => {
    e.preventDefault();
    if (ordering) return;
    setOrdering(true);
    setOrderError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series/${id}/episodes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          idea: idea.trim(),
          user_requirement: userRequirement.trim(),
          music_enabled: musicEnabled,
          dialogue_enabled: dialogueEnabled,
          lipsync_enabled: dialogueEligible && lipsyncEnabled,
          require_script_approval: requireScriptApproval,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "");
      }
      router.push(localeHref(`/generate/${data.job_id}`));
    } catch (err) {
      setOrderError(friendlyError(err.message) || tr(t, "series_order_failed", "Could not order the next episode"));
    } finally {
      setOrdering(false);
    }
  };

  const handleDelete = async () => {
    if (deleting) return;
    if (typeof window !== "undefined" && !window.confirm(t("series_delete_confirm"))) return;
    setDeleting(true);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/series/${id}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("");
      router.push(localeHref("/series"));
    } catch {
      setError(t("series_delete_failed"));
      setDeleting(false);
    }
  };

  if (authLoading || (fetching && !series && !notFound)) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "var(--mf-stage)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--mf-violet)" }} />
      </div>
    );
  }
  if (!user) return null;

  if (notFound) {
    return (
      <main className="min-h-screen flex items-center justify-center px-6" style={{ backgroundColor: "var(--mf-stage)" }}>
        <div className="text-center">
          <h1 className="text-xl font-bold mb-2" style={{ color: "var(--mf-ink)" }}>{t("series_not_found_title")}</h1>
          <p className="text-sm mb-6" style={{ color: "var(--mf-ink-3)" }}>{t("series_not_found_desc")}</p>
          <Link href="/series" className="mf-btn-primary inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold">
            <ArrowLeft size={15} /> {t("series_back_to_list")}
          </Link>
        </div>
      </main>
    );
  }

  if (!series) return null;

  const settingParts = [series.setting_location, series.setting_time_of_day, series.setting_era].filter(Boolean);

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        <div className="flex items-center justify-between mb-6">
          <Link href="/series" className="inline-flex items-center gap-2 text-sm transition-colors hover:text-violet-soft" style={{ color: "var(--mf-ink-3)" }}>
            <ArrowLeft size={16} /> {t("series_back_to_list")}
          </Link>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg disabled:opacity-50"
            style={{ backgroundColor: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--mf-err-soft)" }}
          >
            <Trash2 size={12} />
            {t("series_delete")}
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

        <h1 className="display text-3xl gradient-text mb-2">{series.title}</h1>
        <p className="text-sm mb-8" style={{ color: "var(--mf-ink-2)" }}>{series.premise}</p>

        {/* Bible */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
          <div className="mf-card p-5" style={{ border: "1px solid rgba(139,92,246,0.1)" }}>
            <p className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--mf-violet-soft)" }}>
              <Sparkles size={12} /> {t("series_bible_cast")}
            </p>
            {series.cast?.length ? (
              <div className="space-y-2">
                {series.cast.map((c, i) => (
                  <div key={i} className="flex items-center gap-2">
                    {c.portrait_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={c.portrait_url} alt={c.name} className="w-8 h-8 rounded-full object-cover" />
                    )}
                    <div>
                      <p className="text-xs font-medium" style={{ color: "var(--mf-ink)" }}>{c.name}</p>
                      {c.wardrobe && <p className="text-[11px]" style={{ color: "var(--mf-ink-4)" }}>{c.wardrobe}</p>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs" style={{ color: "var(--mf-ink-4)" }}>{t("series_bible_no_cast")}</p>
            )}
          </div>

          <div className="mf-card p-5" style={{ border: "1px solid rgba(139,92,246,0.1)" }}>
            <p className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--mf-violet-soft)" }}>
              <MapPin size={12} /> {t("series_bible_setting")}
            </p>
            <p className="text-xs" style={{ color: settingParts.length ? "var(--mf-ink-2)" : "var(--mf-ink-4)" }}>
              {settingParts.length ? settingParts.join(" · ") : "—"}
            </p>
          </div>

          {series.story_so_far && (
            <div className="mf-card p-5 sm:col-span-2" style={{ border: "1px solid rgba(139,92,246,0.1)" }}>
              <p className="text-xs font-semibold mb-2 flex items-center gap-1.5" style={{ color: "var(--mf-violet-soft)" }}>
                <BookOpen size={12} /> {t("series_bible_story_so_far")}
              </p>
              <p className="text-xs leading-relaxed" style={{ color: "var(--mf-ink-2)" }}>{series.story_so_far}</p>
            </div>
          )}

          {series.open_question && (
            <div className="mf-card p-5 sm:col-span-2" style={{ border: "1px solid rgba(232,182,76,0.35)" }}>
              <p className="text-xs font-semibold mb-2 flex items-center gap-1.5" style={{ color: "var(--mf-gold)" }}>
                <HelpCircle size={12} /> {t("series_bible_open_question")}
              </p>
              <p className="text-xs leading-relaxed" style={{ color: "var(--mf-ink)" }}>{series.open_question}</p>
            </div>
          )}
        </div>

        {/* Episodes */}
        {series.episodes?.length > 0 && (
          <div className="space-y-3 mb-8">
            {reviewError && (
              <p className="text-xs" style={{ color: "var(--mf-err-soft)" }}>{reviewError}</p>
            )}
            {series.episodes.map((ep) => (
              <EpisodeRow
                key={ep.number}
                episode={ep}
                onConfirm={handleConfirm}
                onReject={handleReject}
                busy={reviewingNumber === ep.number}
              />
            ))}
          </div>
        )}

        {/* Order next episode */}
        {pendingEpisode && (
          <div
            className="mb-4 px-4 py-3 rounded-xl text-xs"
            style={{ backgroundColor: "rgba(232,182,76,0.08)", border: "1px solid rgba(232,182,76,0.35)", color: "var(--mf-gold)" }}
          >
            {tr(
              t,
              "series_order_blocked_pending",
              `Confirm or reject episode ${pendingEpisode.number} before ordering the next one.`,
              { n: pendingEpisode.number }
            )}
          </div>
        )}
        <form
          onSubmit={handleOrder}
          className="glass rounded-2xl p-6 space-y-4"
          style={pendingEpisode ? { opacity: 0.5, pointerEvents: "none" } : undefined}
        >
          <h2 className="text-sm font-bold" style={{ color: "var(--mf-ink)" }}>
            {tr(t, "series_order_title", "Order the next episode")}
          </h2>
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder={t("series_order_idea_ph")}
            rows={2}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
          />
          <textarea
            value={userRequirement}
            onChange={(e) => setUserRequirement(e.target.value)}
            placeholder={t("series_order_requirement_ph")}
            rows={2}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
          />
          <div className="flex flex-wrap gap-4 text-xs" style={{ color: "var(--mf-ink-2)" }}>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={musicEnabled} onChange={(e) => setMusicEnabled(e.target.checked)} />
              {t("form_music_toggle") || "Music"}
            </label>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={dialogueEnabled} onChange={(e) => setDialogueEnabled(e.target.checked)} />
              {t("form_dialogue_toggle") || "Dialogue"}
            </label>
            {dialogueEligible && (
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={lipsyncEnabled} onChange={(e) => setLipsyncEnabled(e.target.checked)} />
                {t("form_lipsync_toggle") || "Lip sync"}
              </label>
            )}
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={requireScriptApproval}
                onChange={(e) => setRequireScriptApproval(e.target.checked)}
              />
              {t("series_order_script_approval")}
            </label>
          </div>
          {orderError && <p className="text-xs" style={{ color: "var(--mf-err-soft)" }}>{orderError}</p>}
          <button
            type="submit"
            disabled={ordering || !!pendingEpisode}
            className="mf-btn-primary inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold disabled:opacity-50"
          >
            {ordering ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {tr(t, "series_order_submit", `Order Episode ${series.next_episode}`, { n: series.next_episode })}
          </button>
        </form>
      </div>
    </main>
  );
}

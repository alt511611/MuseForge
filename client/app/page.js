"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import IdeaForm from "../components/IdeaForm";
import {
  Film,
  Zap,
  GitBranch,
  Layers,
  Sparkles,
  Users,
  Camera,
  Wand2,
  ArrowRight,
  PlayCircle,
  Rocket,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { friendlyError } from "../utils/errorMessages";

// ── Örnek fikirler — tek tıkla forma dolar ──────────────────────────────────
// TopView.ai'daki "tıkla, hemen dene" örnek prompt kartlarından ilham alındı;
// burada MuseForge'un kendi mikro-drama üretim akışına uyarlanmıştır.
const EXAMPLE_PROMPTS = [
  "Kayıp bir denizci, fırtınadan sonra ıssız bir adada antik bir kapı bulur.",
  "İki eski dost, 20 yıl sonra aynı trende karşılaşır ve geçmişleriyle yüzleşir.",
  "Bir dedektif, yağmurlu bir gece neon ışıklı bir şehirde bir gölgeyi takip eder.",
  "Genç bir astronot, terk edilmiş bir uzay istasyonunda büyüyen gizemli bir bahçe keşfeder.",
  "Bir robot, sahibinin son isteğini yerine getirmek için tehlikeli bir yolculuğa çıkar.",
];

// ── Tür şablonları — kart olarak gösterilir, tıklanınca fikir + stil dolar ──
const GENRE_TEMPLATES = [
  {
    key: "scifi",
    label: "Bilim Kurgu",
    idea: "Bir mühendis, uzak bir gezegende insanlığın son sinyalini çözmeye çalışır.",
    style: "Sci-Fi",
    directorStyle: "cinematic_balanced",
    gradient: "linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%)",
  },
  {
    key: "romance",
    label: "Romantik Drama",
    idea: "Bir ressam ile bir müzisyen, yağmurlu bir şehirde tesadüfen tanışır ve birbirlerine aşık olur.",
    style: "Romance",
    directorStyle: "intimate_closeup",
    gradient: "linear-gradient(135deg, #be185d 0%, #7c3aed 100%)",
  },
  {
    key: "thriller",
    label: "Gerilim",
    idea: "Bir gazeteci, büyük bir şirketin sırrını ortaya çıkardıktan sonra takip edilmeye başlar.",
    style: "Noir",
    directorStyle: "noir_mystery",
    gradient: "linear-gradient(135deg, #18181b 0%, #7c3aed 100%)",
  },
  {
    key: "fantasy",
    label: "Fantastik",
    idea: "Genç bir çırak, büyülü bir ormanda kayıp bir krallığın anahtarını arar.",
    style: "Fantasy",
    directorStyle: "cinematic_balanced",
    gradient: "linear-gradient(135deg, #065f46 0%, #7c3aed 100%)",
  },
  {
    key: "action",
    label: "Aksiyon",
    idea: "Emekli bir ajan, kızını kurtarmak için 24 saat içinde eski düşmanlarıyla yüzleşir.",
    style: "Cinematic",
    directorStyle: "dynamic_action",
    gradient: "linear-gradient(135deg, #991b1b 0%, #7c3aed 100%)",
  },
  {
    key: "anime",
    label: "Anime",
    idea: "Bir öğrenci, okulunun bodrumunda gizli bir portal keşfeder ve başka bir dünyaya geçer.",
    style: "Anime",
    directorStyle: "anime_expressive",
    gradient: "linear-gradient(135deg, #9d174d 0%, #7c3aed 100%)",
  },
];

const FEATURES = [
  {
    icon: Users,
    title: "Karakter Tutarlılığı Kilidi",
    desc: "Her karakter için bir kez üretilen referans portre, tüm sahneler boyunca aynı kalır — istediğinizde kendi fotoğrafınızı da kilitleyebilirsiniz.",
  },
  {
    icon: Camera,
    title: "Cinema Studio",
    desc: "Slow Cinematic, Handheld Kinetic, Noir Mystery gibi yönetmen presetleri; kamera hareketini ve çekim dilini otomatik olarak yönlendirir.",
  },
  {
    icon: GitBranch,
    title: "Çok Ajanlı Pipeline",
    desc: "Senarist, storyboard sanatçısı ve görsel/video üretim ajanları birlikte çalışarak fikrinizi uçtan uca bir videoya dönüştürür.",
  },
  {
    icon: Rocket,
    title: "Demo Modu",
    desc: "API anahtarı olmadan bile tüm pipeline'ı deneyebilir, gerçek üretime geçmeden önce akışı görebilirsiniz.",
  },
];

const HOW_IT_WORKS = [
  { icon: Sparkles, title: "Fikrinizi yazın", desc: "Tek cümlelik bir fikir ya da tam bir senaryo — ikisi de yeterli." },
  { icon: GitBranch, title: "Senarist ve storyboard", desc: "AI ajanları sahneleri, karakterleri ve çekimleri planlar." },
  { icon: Wand2, title: "Kare ve video üretimi", desc: "Her çekim için kare üretilir, ardından sinematik videoya dönüştürülür." },
  { icon: PlayCircle, title: "İzleyin, indirin", desc: "Tamamlanan videoyu izleyin, indirin veya paylaşın." },
];

const FAQ = [
  { q: "Karakter fotoğrafımı yüklemem zorunlu mu?", a: "Hayır, tamamen opsiyonel. Yüklemezseniz AI, karakterler için otomatik bir referans portre üretir ve bunu tüm sahneler boyunca tutarlı tutar." },
  { q: "Demo modu gerçek üretimden farklı mı?", a: "Demo modunda API anahtarı olmadan tüm pipeline'ı (senarist, storyboard, kare/video üretimi) yer tutucu görsellerle deneyebilirsiniz. Gerçek video üretimi için bir MuAPI anahtarı gerekir." },
  { q: "Kaç sahne üretebilirim?", a: "Bir seferde 2 ile 5 sahne arasında üretim yapabilirsiniz; sahne sayısı arttıkça üretim süresi de artar." },
  { q: "Üretilen video bana mı ait olur?", a: "Evet. Platformda ürettiğiniz videolar size lisanslanır ve kişisel/ticari kullanım için serbesttir." },
];

export default function HomePage() {
  const router = useRouter();
  const { getAccessToken } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [prefill, setPrefill] = useState(null);
  const formRef = useRef(null);

  const scrollToForm = (data) => {
    setPrefill({ ...data, _ts: Date.now() });
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleSubmit = async (formData) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const token = await getAccessToken();
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(formData),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "İşlem başlatılamadı");
      }
      const data = await res.json();
      router.push(`/generate/${data.job_id}`);
    } catch (err) {
      setError(friendlyError(err.message));
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] rounded-full opacity-20"
            style={{ background: "radial-gradient(ellipse at center, #7c3aed 0%, transparent 70%)", filter: "blur(60px)" }}
          />
        </div>
        <div className="relative max-w-5xl mx-auto px-6 pt-16 pb-12 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-6"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)", color: "#a78bfa" }}>
            <Zap size={12} />
            Powered by MuAPI &amp; Claude AI
          </div>
          <h1 className="text-6xl md:text-7xl font-black tracking-tight mb-6">
            <span className="gradient-text">MuseForge</span>
          </h1>
          <p className="text-xl md:text-2xl font-light mb-3" style={{ color: "#94a3b8" }}>
            Fikirden Sinematik Videoya — Tek Ajanlı Stüdyo
          </p>
          <p className="text-base max-w-2xl mx-auto mb-10" style={{ color: "#64748b" }}>
            Bir fikir yazın. Çok ajanlı pipeline senaryoyu yazar, storyboard tasarlar,
            kareleri üretir ve eksiksiz bir sinematik video oluşturur — otomatik olarak.
          </p>

          {/* Örnek fikir çipleri — tıklanınca doğrudan forma dolar */}
          <div className="flex flex-wrap justify-center gap-2 max-w-3xl mx-auto mb-10">
            {EXAMPLE_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => scrollToForm({ idea: p })}
                className="px-3.5 py-2 rounded-full text-xs text-left transition-all"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8", maxWidth: "280px" }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#7c3aed"; e.currentTarget.style.color = "#e2e8f0"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#22223a"; e.currentTarget.style.color = "#94a3b8"; }}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap justify-center gap-3 mb-4">
            {[
              { icon: <Film size={14} />, label: "Senarist Ajan" },
              { icon: <GitBranch size={14} />, label: "Storyboard Sanatçısı" },
              { icon: <Layers size={14} />, label: "Kare Üretici" },
              { icon: <Zap size={14} />, label: "Video Üretici" },
            ].map((f) => (
              <div key={f.label} className="flex items-center gap-2 px-4 py-2 rounded-full text-sm"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
                <span style={{ color: "#7c3aed" }}>{f.icon}</span>
                {f.label}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Tür şablonları — bol örnek, tek tıkla dene ──────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold mb-2" style={{ color: "#e2e8f0" }}>Bir tür seçin, hemen deneyin</h2>
          <p className="text-sm" style={{ color: "#64748b" }}>
            Her kart, fikri ve görsel stili sizin için önceden dolduran hazır bir başlangıç noktasıdır.
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {GENRE_TEMPLATES.map((g) => (
            <button
              key={g.key}
              type="button"
              onClick={() => scrollToForm({ idea: g.idea, style: g.style, directorStyle: g.directorStyle })}
              className="relative overflow-hidden rounded-2xl p-5 text-left transition-transform hover:scale-[1.02]"
              style={{ background: g.gradient, minHeight: "140px" }}
            >
              <div className="absolute inset-0" style={{ backgroundColor: "rgba(10,10,15,0.35)" }} />
              <div className="relative">
                <span className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold mb-8"
                  style={{ backgroundColor: "rgba(10,10,15,0.4)", color: "#fff" }}>
                  {g.label}
                </span>
                <p className="text-sm leading-snug" style={{ color: "rgba(255,255,255,0.9)" }}>
                  {g.idea}
                </p>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── Nasıl çalışır ────────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-center mb-10" style={{ color: "#e2e8f0" }}>Nasıl çalışır</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6">
          {HOW_IT_WORKS.map((step, i) => (
            <div key={step.title} className="text-center">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)" }}>
                <step.icon size={20} style={{ color: "#a78bfa" }} />
              </div>
              <p className="text-xs font-mono mb-1" style={{ color: "#4b5563" }}>Adım {i + 1}</p>
              <h3 className="text-sm font-semibold mb-1.5" style={{ color: "#e2e8f0" }}>{step.title}</h3>
              <p className="text-xs" style={{ color: "#64748b" }}>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Özellik vitrini ──────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <h2 className="text-2xl font-bold text-center mb-10" style={{ color: "#e2e8f0" }}>Neden MuseForge</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl p-6"
              style={{ backgroundColor: "#12121a", border: "1px solid #1a1a26" }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{ backgroundColor: "rgba(124,58,237,0.15)" }}>
                <f.icon size={18} style={{ color: "#a78bfa" }} />
              </div>
              <h3 className="text-base font-semibold mb-2" style={{ color: "#e2e8f0" }}>{f.title}</h3>
              <p className="text-sm" style={{ color: "#64748b" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Üretim formu ─────────────────────────────────────────────────── */}
      <div ref={formRef} className="max-w-3xl mx-auto px-6 pb-16 scroll-mt-6">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold mb-2" style={{ color: "#e2e8f0" }}>Kendi fikrinizi yazın</h2>
          <p className="text-sm" style={{ color: "#64748b" }}>Yukarıdaki örneklerden birini seçebilir ya da sıfırdan başlayabilirsiniz.</p>
        </div>
        {error && (
          <div className="mb-6 px-4 py-3 rounded-xl text-sm animate-fade-in"
            style={{ backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#fca5a5" }}>
            {error}
          </div>
        )}
        <IdeaForm onSubmit={handleSubmit} isSubmitting={isSubmitting} prefill={prefill} />
      </div>

      {/* ── SSS ──────────────────────────────────────────────────────────── */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <h2 className="text-xl font-bold text-center mb-8" style={{ color: "#e2e8f0" }}>Sık Sorulan Sorular</h2>
        {FAQ.map(({ q, a }) => (
          <div key={q} className="border-b py-5" style={{ borderColor: "#1a1a26" }}>
            <p className="text-sm font-medium mb-1.5" style={{ color: "#e2e8f0" }}>{q}</p>
            <p className="text-sm" style={{ color: "#64748b" }}>{a}</p>
          </div>
        ))}
      </section>

      {/* ── Son CTA ──────────────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-20 text-center">
        <div className="rounded-2xl p-8" style={{ backgroundColor: "#12121a", border: "1px solid #1a1a26" }}>
          <ShieldCheck size={28} style={{ color: "#a78bfa" }} className="mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2" style={{ color: "#e2e8f0" }}>
            Hazır mısınız?
          </h3>
          <p className="text-sm mb-5" style={{ color: "#64748b" }}>
            İster demo modda deneyin, ister planınızı yükseltip gerçek videolar üretin.
          </p>
          <button
            type="button"
            onClick={() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold transition-all"
            style={{ background: "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)", color: "#fff" }}
          >
            Hemen Başla
            <ArrowRight size={16} />
          </button>
        </div>
      </section>

      <footer className="text-center pb-8 text-sm space-y-2" style={{ color: "#374151" }}>
        <p>MuseForge &mdash; Built on MuAPI generative media infrastructure</p>
        <div className="flex justify-center gap-4 text-xs">
          <a href="/pricing" className="hover:text-purple-400 transition-colors">Fiyatlar</a>
          <a href="/legal/privacy" className="hover:text-purple-400 transition-colors">Gizlilik</a>
          <a href="/legal/terms" className="hover:text-purple-400 transition-colors">Koşullar</a>
        </div>
      </footer>
    </main>
  );
}

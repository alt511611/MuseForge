"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Zap, Film, Crown } from "lucide-react";
import CheckoutButton from "../../components/CheckoutButton";
import { useAuth } from "../../contexts/AuthContext";
import Confetti from "../../components/Confetti";

const PLANS = [
  {
    id: "free",
    name: "Free",
    icon: Film,
    price: "₺0",
    period: "/ ay",
    description: "Denemeye başlayın",
    credits: 3,
    features: [
      "3 video / ay",
      "En fazla 3 sahne",
      "Demo modu",
      "16:9 · 9:16 · 1:1 oran",
      "Standart kalite",
    ],
    unavailable: ["HD dışa aktarım", "Öncelikli render"],
    cta: "Mevcut Plan",
    highlight: false,
  },
  {
    id: "creator",
    name: "Creator",
    icon: Zap,
    price: "₺299",
    period: "/ ay",
    description: "İçerik üreticiler için",
    credits: 30,
    features: [
      "30 video / ay",
      "En fazla 5 sahne",
      "Tüm director presets",
      "Tüm en-boy oranları",
      "Öncelikli render kuyruğu",
    ],
    unavailable: ["HD dışa aktarım"],
    cta: "Creator'a Geç",
    highlight: true,
    badge: "En Popüler",
  },
  {
    id: "pro",
    name: "Pro",
    icon: Crown,
    price: "₺799",
    period: "/ ay",
    description: "Profesyoneller için",
    credits: 150,
    features: [
      "150 video / ay",
      "En fazla 5 sahne",
      "Tüm director presets",
      "Tüm en-boy oranları",
      "HD dışa aktarım",
      "Öncelikli render kuyruğu",
      "API erişimi (yakında)",
    ],
    unavailable: [],
    cta: "Pro'ya Geç",
    highlight: false,
  },
];

export default function PricingPage() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const successPlan = searchParams.get("plan");
  const [confetti, setConfetti] = useState(false);

  useEffect(() => {
    if (success) {
      setConfetti(true);
      setTimeout(() => setConfetti(false), 5000);
    }
  }, [success]);

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <Confetti active={confetti} />

      {/* Success banner */}
      {success && (
        <div
          className="py-3 text-center text-sm font-medium animate-fade-in"
          style={{ background: "linear-gradient(90deg,rgba(34,197,94,0.2),rgba(34,197,94,0.1))", color: "#86efac", borderBottom: "1px solid rgba(34,197,94,0.2)" }}
        >
          🎉 {successPlan ? `${successPlan.charAt(0).toUpperCase() + successPlan.slice(1)} planına` : "Aboneliğinize"} hoş geldiniz! Kredileriniz hesabınıza eklendi.
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="text-center mb-14">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-5"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)", color: "#a78bfa" }}
          >
            <Zap size={12} /> Planlar ve Fiyatlar
          </div>
          <h1 className="text-4xl md:text-5xl font-black tracking-tight mb-4">
            <span className="gradient-text">İhtiyacınıza Uygun</span>
            <br />
            <span style={{ color: "#e2e8f0" }}>Bir Plan Seçin</span>
          </h1>
          <p className="text-base max-w-xl mx-auto" style={{ color: "#64748b" }}>
            Tüm planlar iptal edilebilir. İlk ay ücretsiz krediyle başlayın.
          </p>
        </div>

        {/* Plans grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => {
            const Icon = plan.icon;
            return (
              <div
                key={plan.id}
                className="relative glass rounded-2xl p-7 flex flex-col transition-all"
                style={{
                  border: plan.highlight ? "1px solid rgba(124,58,237,0.5)" : "1px solid rgba(124,58,237,0.1)",
                  boxShadow: plan.highlight ? "0 0 40px rgba(124,58,237,0.15)" : "none",
                }}
              >
                {plan.badge && (
                  <div
                    className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full text-xs font-semibold"
                    style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
                  >
                    {plan.badge}
                  </div>
                )}

                {/* Plan header */}
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: plan.highlight ? "rgba(124,58,237,0.2)" : "#1a1a26" }}
                  >
                    <Icon size={20} style={{ color: plan.highlight ? "#a78bfa" : "#64748b" }} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold" style={{ color: "#e2e8f0" }}>{plan.name}</h2>
                    <p className="text-xs" style={{ color: "#64748b" }}>{plan.description}</p>
                  </div>
                </div>

                {/* Price */}
                <div className="mb-6">
                  <span className="text-4xl font-black" style={{ color: "#e2e8f0" }}>{plan.price}</span>
                  <span className="text-sm ml-1" style={{ color: "#64748b" }}>{plan.period}</span>
                  <p className="text-xs mt-1" style={{ color: "#475569" }}>{plan.credits} video / ay</p>
                </div>

                {/* Features */}
                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm" style={{ color: "#94a3b8" }}>
                      <Check size={14} style={{ color: "#22c55e", flexShrink: 0 }} />
                      {f}
                    </li>
                  ))}
                  {plan.unavailable.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm line-through" style={{ color: "#374151" }}>
                      <Check size={14} style={{ color: "#374151", flexShrink: 0 }} />
                      {f}
                    </li>
                  ))}
                </ul>

                {/* CTA */}
                {plan.id === "free" ? (
                  <Link
                    href={user ? "/" : "/login"}
                    className="w-full py-3 rounded-xl text-sm font-semibold text-center block transition-all"
                    style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#64748b" }}
                  >
                    {user ? "Mevcut Plan" : "Ücretsiz Başla"}
                  </Link>
                ) : (
                  <CheckoutButton
                    plan={plan.id}
                    className={`w-full py-3 rounded-xl text-sm font-semibold ${plan.highlight ? "" : ""}`}
                    style={
                      plan.highlight
                        ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }
                        : { backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8" }
                    }
                  >
                    {plan.cta}
                  </CheckoutButton>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="mt-16 max-w-2xl mx-auto">
          <h2 className="text-xl font-bold text-center mb-8" style={{ color: "#e2e8f0" }}>Sık Sorulan Sorular</h2>
          {[
            { q: "Kredi ne zaman yenilenir?", a: "Krediler aylık abonelik döneminin başında yenilenir. Kullanılmayan krediler bir sonraki aya devretmez." },
            { q: "İstediğim zaman iptal edebilir miyim?", a: "Evet. Aboneliğinizi istediğiniz zaman iptal edebilirsiniz. İptal, bir sonraki fatura döneminden itibaren geçerlidir." },
            { q: "Hangi ödeme yöntemleri kabul ediliyor?", a: "Visa, Mastercard ve diğer yaygın kartlar Stripe altyapısı üzerinden güvenle işlenir." },
            { q: "Üretilen videolar bana mı ait?", a: "Evet. Platformda ürettiğiniz videolar size lisanslanır ve kişisel/ticari kullanım için serbesttir." },
          ].map(({ q, a }) => (
            <div key={q} className="border-b py-5" style={{ borderColor: "#1a1a26" }}>
              <p className="text-sm font-medium mb-1.5" style={{ color: "#e2e8f0" }}>{q}</p>
              <p className="text-sm" style={{ color: "#64748b" }}>{a}</p>
            </div>
          ))}
        </div>

        {/* Legal links */}
        <div className="text-center mt-12 text-xs space-x-4" style={{ color: "#374151" }}>
          <Link href="/legal/terms" className="hover:text-purple-400">Kullanım Koşulları</Link>
          <Link href="/legal/privacy" className="hover:text-purple-400">Gizlilik Politikası</Link>
        </div>
      </div>
    </main>
  );
}

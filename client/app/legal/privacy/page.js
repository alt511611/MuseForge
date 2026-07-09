import Link from "next/link";

export const metadata = {
  title: "Gizlilik Politikası — MuseForge",
  description: "KVKK kapsamında kişisel verilerin işlenmesine ilişkin aydınlatma metni.",
};

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>
      {children}
    </div>
  </section>
);

export default function PrivacyPage() {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          ← Ana Sayfa
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">Gizlilik Politikası</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>Son güncelleme: {new Date().toLocaleDateString("tr-TR")}</p>

        <div className="glass rounded-2xl p-8">
          <Section title="1. Veri Sorumlusu">
            <p>
              MuseForge ("Şirket", "biz"), 6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") kapsamında
              veri sorumlusu sıfatıyla hareket etmektedir. Bu metin, hangi kişisel verilerin toplandığını,
              nasıl kullanıldığını ve haklarınızı açıklamaktadır.
            </p>
          </Section>

          <Section title="2. Toplanan Kişisel Veriler">
            <ul className="list-disc list-inside space-y-1">
              <li><strong style={{ color: "#e2e8f0" }}>Kimlik / İletişim:</strong> Kayıt sırasında sağlanan e-posta adresi.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Kullanım Verileri:</strong> Oluşturulan video talepleri, tercihler, oturum bilgileri.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Ödeme Bilgileri:</strong> Ödeme işlemleri Stripe tarafından gerçekleştirilir; kart bilgileri MuseForge sunucularında saklanmaz.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Teknik Veriler:</strong> IP adresi, tarayıcı türü, sayfa etkileşimleri (analitik için).</li>
              <li><strong style={{ color: "#e2e8f0" }}>Çerezler:</strong> Oturum yönetimi ve tercih hatırlama amacıyla kullanılır.</li>
            </ul>
          </Section>

          <Section title="3. İşleme Amaçları ve Hukuki Dayanaklar">
            <ul className="list-disc list-inside space-y-1">
              <li>Hizmetin sağlanması ve hesap yönetimi (sözleşmenin ifası).</li>
              <li>Ödeme ve abonelik yönetimi (sözleşmenin ifası / yasal yükümlülük).</li>
              <li>Hizmet güvenliği ve dolandırıcılık önleme (meşru menfaat).</li>
              <li>Teknik sorunların tespiti ve giderilmesi (meşru menfaat).</li>
              <li>Pazarlama iletişimi (yalnızca açık rızayla).</li>
            </ul>
          </Section>

          <Section title="4. Veri Paylaşımı">
            <p>
              Kişisel verileriniz; hizmet sağlayıcılar (Supabase, Stripe, Vercel, Render), yasal
              yükümlülükler ve açık rızanız dışında üçüncü taraflarla paylaşılmaz. Yurt dışına aktarım,
              KVKK madde 9 kapsamında yeterli koruma tedbirleri alınarak gerçekleştirilir.
            </p>
          </Section>

          <Section title="5. Saklama Süresi">
            <ul className="list-disc list-inside space-y-1">
              <li>Hesap verileri: hesap kapatılana dek, ardından 6 ay.</li>
              <li>Ödeme kayıtları: yasal zorunluluk gereği 10 yıl.</li>
              <li>Teknik günlükler: 90 gün.</li>
            </ul>
          </Section>

          <Section title="6. KVKK Kapsamındaki Haklarınız">
            <p>KVKK madde 11 uyarınca şu haklara sahipsiniz:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Kişisel verilerinizin işlenip işlenmediğini öğrenme.</li>
              <li>İşlenen verilere ilişkin bilgi talep etme.</li>
              <li>İşlenme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenme.</li>
              <li>Yurt içinde/dışında aktarıldığı üçüncü kişileri bilme.</li>
              <li>Eksik/yanlış işlenmesi halinde düzeltme talep etme.</li>
              <li>Silme veya yok etme talep etme.</li>
              <li>Otomatik sistemler aracılığıyla aleyhinize sonuç doğuran kararı itiraz etme.</li>
              <li>Zarara uğranması halinde zararın giderilmesini talep etme.</li>
            </ul>
            <p className="mt-2">
              Talepler için:{" "}
              <a href="mailto:privacy@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>
                privacy@museforge.ai
              </a>
            </p>
          </Section>

          <Section title="7. Çerezler">
            <p>
              Zorunlu çerezler oturum yönetimi için kullanılır. Analitik çerezler için sayfanın altındaki
              çerez banner'ından tercihlerinizi yönetebilirsiniz.
            </p>
          </Section>

          <Section title="8. Değişiklikler">
            <p>
              Bu politika güncellenebilir. Önemli değişiklikler e-posta ile bildirilecektir.
              Güncel sürüm her zaman bu sayfada yayımlanır.
            </p>
          </Section>
        </div>

        <div className="mt-6 flex gap-4 text-xs" style={{ color: "#475569" }}>
          <Link href="/legal/terms" className="underline hover:text-purple-400">Kullanım Koşulları</Link>
          <Link href="/" className="underline hover:text-purple-400">Ana Sayfa</Link>
        </div>
      </div>
    </main>
  );
}

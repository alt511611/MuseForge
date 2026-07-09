import Link from "next/link";

export const metadata = {
  title: "Kullanım Koşulları — MuseForge",
  description: "MuseForge hizmetini kullanmadan önce lütfen kullanım koşullarını okuyunuz.",
};

const Section = ({ title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-semibold mb-3" style={{ color: "#a78bfa" }}>{title}</h2>
    <div className="text-sm leading-relaxed space-y-2" style={{ color: "#94a3b8" }}>
      {children}
    </div>
  </section>
);

export default function TermsPage() {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link href="/" className="text-sm mb-8 inline-block hover:text-purple-400 transition-colors" style={{ color: "#64748b" }}>
          ← Ana Sayfa
        </Link>

        <h1 className="text-3xl font-black gradient-text mb-2">Kullanım Koşulları</h1>
        <p className="text-xs mb-10" style={{ color: "#475569" }}>Son güncelleme: {new Date().toLocaleDateString("tr-TR")}</p>

        <div className="glass rounded-2xl p-8">
          <Section title="1. Hizmetin Tanımı">
            <p>
              MuseForge, yapay zeka destekli video oluşturma hizmeti sunan bir platformdur. Hizmete
              erişim sağlayarak bu koşulları kabul etmiş sayılırsınız.
            </p>
          </Section>

          <Section title="2. Hesap Oluşturma ve Güvenlik">
            <ul className="list-disc list-inside space-y-1">
              <li>Hesap açmak için 18 yaşını doldurmuş olmanız gerekir.</li>
              <li>Hesap bilgilerinizin gizliliğini korumak sizin sorumluluğunuzdadır.</li>
              <li>Hesabınız üzerinden gerçekleştirilen tüm işlemlerden siz sorumlusunuzdur.</li>
              <li>Şüpheli aktivite durumunda derhal bizimle iletişime geçiniz.</li>
            </ul>
          </Section>

          <Section title="3. Kabul Edilemez Kullanım">
            <p>Şu amaçlarla kullanım kesinlikle yasaktır:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Yasa dışı, aldatıcı veya zarar verici içerik üretmek.</li>
              <li>Deepfake veya kimlik sahteciliğine yönelik içerik oluşturmak.</li>
              <li>Telif hakkı veya fikri mülkiyet ihlali.</li>
              <li>Sisteme yetkisiz erişim veya servis aksamasına yol açmak.</li>
              <li>18 yaş altı için uygunsuz içerik üretmek.</li>
            </ul>
          </Section>

          <Section title="4. Fikri Mülkiyet">
            <ul className="list-disc list-inside space-y-1">
              <li><strong style={{ color: "#e2e8f0" }}>Sizin içeriğiniz:</strong> Platforma yüklediğiniz fikir ve metin girdilerinin fikri mülkiyeti size aittir.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Üretilen içerik:</strong> Abonelik kapsamında oluşturulan videolar kişisel ve ticari kullanım için size lisanslanır. Üçüncü taraf AI sağlayıcı koşulları saklıdır.</li>
              <li><strong style={{ color: "#e2e8f0" }}>Platform:</strong> MuseForge markası, yazılımı ve arayüzü şirkete aittir; çoğaltılamaz.</li>
            </ul>
          </Section>

          <Section title="5. Ödeme ve Abonelik">
            <ul className="list-disc list-inside space-y-1">
              <li>Ücretli planlar aylık veya yıllık faturalandırılır.</li>
              <li>İptal, bir sonraki fatura döneminden itibaren geçerlidir; kıst iade yapılmaz.</li>
              <li>Ödemeler Stripe altyapısıyla güvenle işlenir.</li>
              <li>Fiyat değişikliklerinde 30 gün öncesinden bildirim yapılır.</li>
              <li>Ücretsiz plandaki krediler aylık sıfırlanmaz; biter, yenilenmez.</li>
            </ul>
          </Section>

          <Section title="6. Sorumluluk Sınırlandırması">
            <p>
              MuseForge, yürürlükteki mevzuatın izin verdiği azami ölçüde; dolaylı, arızi veya
              sonuçsal zararlardan sorumlu değildir. Hizmet "olduğu gibi" sunulmaktadır ve %100 kesintisiz
              çalışma garantisi verilmemektedir.
            </p>
          </Section>

          <Section title="7. Hesap Kapatma">
            <ul className="list-disc list-inside space-y-1">
              <li>Hesabınızı dilediğiniz zaman ayarlar üzerinden kapatabilirsiniz.</li>
              <li>Bu Koşullar'ı ihlal etmeniz halinde hesabınız askıya alınabilir veya kapatılabilir.</li>
              <li>Hesap kapatılması halinde veriler Gizlilik Politikası'nda belirtilen saklama süresi kadar tutulur.</li>
            </ul>
          </Section>

          <Section title="8. Geçerli Hukuk ve Uyuşmazlık Çözümü">
            <p>
              Bu Koşullar Türk Hukuku'na tabidir. Uyuşmazlıklarda İstanbul Mahkemeleri ve
              İcra Daireleri yetkilidir.
            </p>
          </Section>

          <Section title="9. Değişiklikler">
            <p>
              Koşullar güncellenebilir. Önemli değişiklikler e-posta ile bildirilecek;
              değişiklik sonrası kullanımınız devam etmesi yeni koşulları kabul anlamına gelir.
            </p>
          </Section>

          <Section title="10. İletişim">
            <p>
              Sorularınız için:{" "}
              <a href="mailto:legal@museforge.ai" className="underline" style={{ color: "#a78bfa" }}>
                legal@museforge.ai
              </a>
            </p>
          </Section>
        </div>

        <div className="mt-6 flex gap-4 text-xs" style={{ color: "#475569" }}>
          <Link href="/legal/privacy" className="underline hover:text-purple-400">Gizlilik Politikası</Link>
          <Link href="/" className="underline hover:text-purple-400">Ana Sayfa</Link>
        </div>
      </div>
    </main>
  );
}

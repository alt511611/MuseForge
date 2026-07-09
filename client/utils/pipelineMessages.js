export const STAGE_MESSAGES = {
  screenwriting: [
    "📝 Senarist fikrini şekle sokuyor...",
    "✍️ Diyaloglar yazılıyor...",
    "🎭 Karakterler hayat buluyor...",
    "📖 Sahne yapısı oluşturuluyor...",
  ],
  portraits: [
    "🎨 Karakter portreleri kilitleniyor...",
    "👤 Tutarlılık için yüzler sabitleniyor...",
    "🖼️ Görsel DNA oluşturuluyor...",
  ],
  storyboard: [
    "🎬 Yönetmen vizyonunu çiziyor...",
    "📐 Kamera açıları planlanıyor...",
    "🎞️ Storyboard kare kare tasarlanıyor...",
  ],
  frames: [
    "🖼️ Sinematik kareler üretiliyor...",
    "✨ Her piksel özenle yerleştiriliyor...",
    "💡 Işık ve gölgeler ayarlanıyor...",
    "🎭 Sahne canlandırılıyor...",
  ],
  video: [
    "🎬 Kareler hareket kazanıyor...",
    "🌀 Animasyon işleniyor...",
    "⚡ Video klipler üretiliyor...",
    "🎥 Sahne hayata geçiriliyor...",
  ],
  assembly: [
    "🔗 Sahneler birleştiriliyor...",
    "✂️ Son kurgu yapılıyor...",
    "🎬 Dramatik akış oluşturuluyor...",
  ],
  music: [
    "🎵 Müzik dramaya ekleniyor...",
    "🎼 Ses atmosferi yerleştiriliyor...",
    "🔊 Final mix hazırlanıyor...",
  ],
  complete: [
    "🎉 Videonuz hazır!",
    "✅ Tüm ajanlar görevini tamamladı!",
  ],
  error: [
    "❌ Bir sorun oluştu.",
    "⚠️ Pipeline beklenmedik bir durumla karşılaştı.",
  ],
};

const INSPIRATION = [
  "✨ Yaratıcılığınızı konuşturuyorsunuz...",
  "🌟 Her büyük film bir fikirle başlar...",
  "🚀 Yapay zeka, hayalinizi gerçeğe dönüştürüyor...",
  "🎨 Sanat + Teknoloji = Sınırsız Olasılık",
  "🎭 Sizin hikayeniz, AI'ın fırçası...",
  "⚡ Saniyeler içinde sinema tarihine geçin...",
];

export function getStageMessage(stage, idx = 0) {
  const msgs = STAGE_MESSAGES[stage];
  if (!msgs) return "";
  return msgs[idx % msgs.length];
}

export function getInspirationMessage(seed = 0) {
  return INSPIRATION[seed % INSPIRATION.length];
}

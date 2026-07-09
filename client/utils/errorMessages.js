const ERROR_MAP = [
  { match: /timeout|timed out|time.?out/i, msg: "⏱️ İşlem zaman aşımına uğradı. Sunucular meşgul olabilir — lütfen tekrar deneyin." },
  { match: /muapi_key|api.?key|not configured|503/i, msg: "🔑 Sunucu henüz yapılandırılmamış. MUAPI_KEY eksik — lütfen yöneticiyle iletişime geçin." },
  { match: /quota|rate.?limit|429/i, msg: "🚦 API kotası aşıldı. Birkaç dakika bekleyip tekrar deneyin." },
  { match: /cancelled/i, msg: "🚫 Video üretimi iptal edildi." },
  { match: /network|fetch|connection/i, msg: "📡 Ağ bağlantısı kesildi. İnternetinizi kontrol edip tekrar deneyin." },
  { match: /401|unauthorized/i, msg: "🔒 Oturum süreniz dolmuş. Lütfen tekrar giriş yapın." },
  { match: /403|forbidden/i, msg: "🚫 Bu işlem için yetkiniz yok." },
  { match: /404|not found/i, msg: "🔍 İşlem bulunamadı. Sayfa yenilenerek tekrar denenebilir." },
];

export function friendlyError(raw) {
  if (!raw) return "Bilinmeyen bir hata oluştu.";
  for (const { match, msg } of ERROR_MAP) {
    if (match.test(raw)) return msg;
  }
  // Trim long internal errors
  const trimmed = raw.length > 120 ? raw.slice(0, 120) + "…" : raw;
  return `❌ ${trimmed}`;
}

# Whop kurulumu — adım adım

MuseForge'u Whop üzerinden satmak için yapılması gereken her şey. Kod tarafı
bitti ([server/whop_integration.py](../server/whop_integration.py),
[server/billing.py](../server/billing.py)); burada anlatılan her şey Whop
panelinde ve Coolify'da yapılacak **operasyon** işi.

Whop paneli sık değişiyor. Menü adları buradakiyle birebir tutmazsa, aşağıdaki
Ek A'daki İngilizce metni Whop'un kendi yapay zekâsına yapıştır — ne
istediğini tam olarak yazar, o sana o günkü ekranı gösterir.

**Değişmemesi gereken tek şey:** planların fiyatları ve kredi karşılıkları.
Kredi sayıları Whop'ta değil kodda tanımlı (`server/billing.py` →
`PLAN_CREDITS`, `CREDIT_PACKAGES`). Whop'ta fiyatı değiştirirsen kod aynı
krediyi vermeye devam eder — yani müşteri ödediğinden farklı kredi alır.

---

## Mevcut durum (15 Eylül 2026, Whop API'den okundu)

Company `biz_Ia2QYWQRKL7rLN` ("MuseForge"), ürün `prod_GVRGdFd5bUwVN`.

| Adım | Durum |
|---|---|
| 1. Company + ürün | ✅ var |
| 2. Yedi plan | ✅ yedisi de doğru fiyat ve tiple duruyor (aşağıdaki tablo) |
| 3. API key | ✅ oluşturuldu, `checkout_configurations` izni çalışıyor (canlı link üretildi) |
| 4. Webhook | ✅ `https://api2.museforge.studio/api/whop-webhook`, enabled, `payment.succeeded` + `membership.deactivated` |
| 5. Coolify değişkenleri | ⬜ **yapılacak** — yereldeki `.env` dolduruldu, production'a girilmedi |
| 6. Supabase migration | ⬜ **yapılacak** — `whop_user_id` / `whop_membership_id` kolonları |
| 7. Uçtan uca test | ⬜ gerçek bir ödeme bekliyor |

Canlı plan id'leri (yereldeki `.env`'e yazıldı):

```
WHOP_PLAN_CREATOR=plan_nyLmAU0GFln8v          # Creator - Monthly   $59 / 30 gün
WHOP_PLAN_PRO=plan_PDGd7fdRRwLZc              # Pro - Monthly       $129 / 30 gün
WHOP_PLAN_CREATOR_ANNUAL=plan_dMnYrA6Ti00Aa   # Creator - Annual    $637 / 365 gün
WHOP_PLAN_PRO_ANNUAL=plan_H0DjqTDZXhnwA       # Pro - Annual        $1393 / 365 gün
WHOP_PLAN_CREDITS_SMALL=plan_ZVWMcb6555Vd4    # 4 Credits           $19 one-time
WHOP_PLAN_CREDITS_MEDIUM=plan_DnzIVw1jctR03   # 12 Credits          $49 one-time
WHOP_PLAN_CREDITS_LARGE=plan_d8D1RpeXYZXR9    # 26 Credits          $99 one-time
```

API hakkında sahada doğrulananlar:

- Liste uçları **`account_id` istiyor**: `GET /api/v1/plans?account_id=biz_...`
  Yoksa 400 "account_id is required" döner.
- `POST /api/v1/checkout_configurations` gerçekten `plan_id` + `metadata` +
  `redirect_url` alıp `purchase_url` döndürüyor; yazdığımız metadata
  (`user_id`, `credit_package`) configuration üzerinde aynen duruyor.
  Test link'i: `ch_6jnSG5tE3MWJENu` (zararsız, silinmesi gerekmiyor).
- Webhook'un iptal event'i bu hesapta **`membership.deactivated`** adıyla
  duruyor, dokümandaki `membership.went_invalid` ile değil. Kod ikisini de
  kabul ediyor (`whop_integration.CANCELLATION_EVENTS`), o yüzden panelde
  değiştirmeye gerek yok.
- API key `ws_` ile **başlamaz**. `ws_...` webhook signing secret'ıdır ve
  `WHOP_WEBHOOK_SECRET`'a girer; API key'i oraya koyarsan her istek 401 döner.

---

## 0. Ön koşullar

- Whop hesabı (whop.com) ve **payout** bilgileri girilmiş olmalı: Whop
  merchant of record olduğu için parayı o tahsil edip sana ödüyor. Şirket
  gerekmiyor, bireysel hesap yeterli — Stripe'a geçme sebebimiz zaten bu.
- Whop komisyonu kart ücretlerinin üstüne ~%3. Fiyatlar bunu karşılayacak
  şekilde belirlenmedi; marj hesabını gözden geçirmek istersen
  `server/billing.py` içindeki `PLAN_CREDITS` yorumuna bak.
- Backend adresi: `https://api2.museforge.studio` (Coolify).

---

## 1. Company ve ürün oluştur

1. Whop → **Create a company** (veya mevcut company'yi kullan). Adı:
   `MuseForge`.
2. Şirketin içinde bir ürün (Whop'ta buna **product / access pass** deniyor)
   oluştur: `MuseForge`.
3. Ürünün teslimat tipi önemli değil — müşteri erişimi bizim uygulamamızda,
   Supabase'deki plan/kredi üzerinden veriliyor. Whop'un iş yükü sadece parayı
   tahsil etmek ve bize webhook atmak. Whop bir Discord/Telegram bağlamanı
   isterse **atla**.

---

## 2. Yedi plan oluştur

Bu tablonun tamamı tek tek oluşturulacak. **Currency: USD**, hepsinde.

| # | Plan adı | Tip | Fiyat | Env değişkeni | Kod ne veriyor |
|---|----------|-----|-------|----------------|----------------|
| 1 | Creator — Monthly | Recurring / monthly | $59 | `WHOP_PLAN_CREATOR` | 16 kredi, 30 gün |
| 2 | Pro — Monthly | Recurring / monthly | $129 | `WHOP_PLAN_PRO` | 36 kredi, 30 gün |
| 3 | Creator — Annual | Recurring / yearly | $637 | `WHOP_PLAN_CREATOR_ANNUAL` | 192 kredi, 365 gün |
| 4 | Pro — Annual | Recurring / yearly | $1393 | `WHOP_PLAN_PRO_ANNUAL` | 432 kredi, 365 gün |
| 5 | 4 Credits | One-time | $19 | `WHOP_PLAN_CREDITS_SMALL` | 4 kredi, 365 gün |
| 6 | 12 Credits | One-time | $49 | `WHOP_PLAN_CREDITS_MEDIUM` | 12 kredi, 365 gün |
| 7 | 26 Credits | One-time | $99 | `WHOP_PLAN_CREDITS_LARGE` | 26 kredi, 365 gün |

Dikkat edilecekler:

- **Yıllık planlar gerçekten yıllık olmalı** (billing period = 1 year), aylık
  fiyatın 12 katı değil. Fiyat sayfası yıllığı %10 indirimli gösteriyor;
  $637 = 59 × 12 × 0.9, $1393 = 129 × 12 × 0.9.
- **Kredi paketleri one-time olmalı**, recurring değil. Yanlışlıkla recurring
  yapılırsa müşteri her ay tekrar çekilir.
- **Trial verme.** Ücretsiz deneme kredileri Supabase'den geliyor (yeni
  kullanıcıya 3 kredi); Whop'ta ayrıca trial açarsan ödeme webhook'u gelmeden
  erişim vermiş olursun ve kredi düşmez.
- Planlar oluştuktan sonra her birinin **plan id**'sini (`plan_...` ile
  başlar) kopyala. Bunlar Adım 5'te gerekli.

---

## 3. API key oluştur

Whop → **Developer / API keys** → yeni key.

Gereken izinler (checkout link'i sunucu tarafında üretiyoruz):

```
checkout_configuration:create
checkout_configuration:basic:read
plan:create
access_pass:create
access_pass:update
```

Çıkan key `WHOP_API_KEY` olacak. **Bir kez gösteriliyor**, kaybedersen yenisini
üretmen gerekir.

---

## 4. Webhook oluştur

Whop → **Developer / Webhooks** → yeni webhook.

- **URL:** `https://api2.museforge.studio/api/whop-webhook`
- **Events (sadece bu ikisi yeterli):**
  - `payment.succeeded` — hem ilk satın alma hem her yenileme buradan geliyor
    (`billing_reason` ayırıyor: `subscription_create`, `subscription_cycle`,
    `one_time`).
  - `membership.went_invalid` — abonelik bitti/iptal edildi; kiralanmış
    kredileri geri alıyoruz, satın alınmış paketlere dokunmuyoruz.
  - İstersen `payment.failed` da ekleyebilirsin; şu an endpoint onu sessizce
    kabul ediyor (henüz bildirim göndermiyoruz).
- **Signing secret** (`ws_...` ile başlar) oluşturulurken **bir kez**
  gösteriliyor. Hemen kopyala → `WHOP_WEBHOOK_SECRET`.

Webhook'u test etmeden önce Adım 5 ve 6 bitmiş olmalı, yoksa Whop'un test
gönderimi 400 döner ve arka arkaya başarısız olursa Whop webhook'u otomatik
devre dışı bırakır (72 saat / 10+ başarısız gönderim).

---

## 5. Coolify'da ortam değişkenleri

Backend servisine ekle, sonra **redeploy**:

```
PAYMENT_PROVIDER=whop

WHOP_API_KEY=<adım 3>
WHOP_WEBHOOK_SECRET=ws_<adım 4>

WHOP_PLAN_CREATOR=plan_...
WHOP_PLAN_PRO=plan_...
WHOP_PLAN_CREATOR_ANNUAL=plan_...
WHOP_PLAN_PRO_ANNUAL=plan_...
WHOP_PLAN_CREDITS_SMALL=plan_...
WHOP_PLAN_CREDITS_MEDIUM=plan_...
WHOP_PLAN_CREDITS_LARGE=plan_...
```

Stripe değişkenlerini **silme**. Şirket kurulduğunda geri dönüş tek satır:
`PAYMENT_PROVIDER=stripe`. Veri taşıma yok — `whop_*` ve `stripe_*` kolonları
`public.profiles` üzerinde yan yana duruyor.

Sandbox'ta denemek istersen (önerilir):
`WHOP_API_BASE=https://sandbox-api.whop.com/api/v1`

---

## 6. Supabase migration

Supabase → SQL Editor → [supabase_migration.sql](../supabase_migration.sql)
dosyasının tamamını çalıştır. Yeniden çalıştırmak güvenli; bu sürümde sadece
şunlar ekleniyor:

```sql
alter table public.profiles add column if not exists whop_user_id text;
alter table public.profiles add column if not exists whop_membership_id text;
create index if not exists profiles_whop_membership_id_idx
  on public.profiles (whop_membership_id);
```

`whop_membership_id`, Stripe'daki `stripe_customer_id`'nin karşılığı: yenileme
ve iptal webhook'ları profili bununla buluyor. Bu kolon olmadan ilk satın alma
çalışır, **ikinci yılın yenilemesi krediyi kimseye yazamaz**.

---

## 7. Uçtan uca test

Sırasıyla:

1. **Checkout açılıyor mu?** Siteden Pro → Annual → "Get started". Whop
   checkout sayfasına düşmelisin. Düşmüyorsan cevap 400'dür ve hata mesajı
   hangi `WHOP_PLAN_*` değişkeninin eksik olduğunu yazar.
2. **Ödemeyi yap** (sandbox'ta test kartı, canlıda kendi kartınla en ucuz
   paket — $19).
3. **Webhook geldi mi?** Whop → Webhooks → Deliveries: `payment.succeeded`
   200 dönmeli.
4. **Kredi yazıldı mı?** Supabase:
   ```sql
   select * from public.credit_ledger order by created_at desc limit 5;
   select id, plan, credits, whop_membership_id from public.profiles
   where email = '<test hesabın>';
   ```
   Beklenen: ledger'da doğru miktarda satır, `whop_membership_id` dolu, plan
   güncellenmiş.
5. **İki kez yazılmadı mı?** Whop → Deliveries → aynı event'i **Resend**.
   İkinci gönderim 200 dönmeli ama ledger'a yeni satır **eklenmemeli**.
6. **İptal.** Whop'tan membership'i iptal et → `membership.went_invalid` →
   plan `free`, abonelik kredileri sıfırlanır, satın alınmış paket kredileri
   durur.

---

## 8. Bir şey ters giderse

| Belirti | Sebep | Çözüm |
|---|---|---|
| Her webhook 400, log'da "signature verification failed" | `WHOP_WEBHOOK_SECRET` yanlış veya başka bir webhook'un secret'ı | Whop'ta webhook'u sil, yeniden oluştur, yeni secret'ı gir |
| Her webhook 400, log'da "WHOP_WEBHOOK_SECRET is not configured" | Değişken Coolify'a girilmemiş veya redeploy edilmemiş | Gir ve redeploy et |
| 400, "timestamp is … out of date" | Sunucu saati kaymış | Sunucuda NTP |
| 200 dönüyor ama kredi yok; log'da "PAID but NOT credited" | Ödeme, bizim ürettiğimiz link yerine Whop mağazasından yapılmış — metadata'da `user_id` yok | Krediyi elle ver (`select public.grant_credits('<user_id>', <adet>, 'credit_purchase', 365);`) ve satışı hep uygulama içindeki butondan yaptır |
| Checkout 400, "No Whop plan configured for…" | O plan/interval için `WHOP_PLAN_*` eksik | Adım 2 tablosundaki env değişkenini gir |
| Kredi miktarı beklenenden farklı | Whop'ta fiyat değişmiş, kod değişmemiş | `server/billing.py` ile Whop planlarını karşılaştır |

Log'da her checkout'ta hangi işlemcinin seçildiği yazar (`payments` satırı) —
"acaba Whop mu Stripe mı çalışıyor" sorusunu tahmin etmeye gerek yok.

---

## Ek A — Whop'un yapay zekâsına yapıştırılacak metin

```
I'm setting up a SaaS product on Whop. My backend is already built and calls
the Whop API; I only need help doing the following in the Whop dashboard.
Please give me the exact click path for each step.

1. Create a company called "MuseForge" and one product under it. Access is
   granted inside my own app (I use the webhook), so the product needs no
   Discord/Telegram integration and no free trial.

2. Create these 7 plans under that product, all in USD:
   - "Creator - Monthly", recurring, billed every 1 month, $59
   - "Pro - Monthly", recurring, billed every 1 month, $129
   - "Creator - Annual", recurring, billed every 1 year, $637
   - "Pro - Annual", recurring, billed every 1 year, $1393
   - "4 Credits", one-time payment, $19
   - "12 Credits", one-time payment, $49
   - "26 Credits", one-time payment, $99
   Then show me where to copy each plan's plan_... id.

3. Create an API key with these permissions:
   checkout_configuration:create, checkout_configuration:basic:read,
   plan:create, access_pass:create, access_pass:update.
   I use it server-side to POST /api/v1/checkout_configurations with a
   plan_id, a metadata object and a redirect_url, and I read purchase_url
   from the response. Confirm this is the right endpoint and permission set
   for that, and tell me if anything else is required.

4. Create a webhook pointing to
   https://api2.museforge.studio/api/whop-webhook
   subscribed to payment.succeeded and membership.went_invalid.
   Show me where the signing secret is displayed, and confirm:
   - which headers you send for signature verification, and exactly how the
     signed string is built,
   - whether the signing secret (ws_...) should be used as raw bytes or
     base64-decoded after the prefix when computing the HMAC,
   - that the metadata I attach to a checkout configuration is copied onto
     the payment and the membership, and is present on renewal payments,
   - the exact JSON shape of payment.succeeded, specifically where I find
     billing_reason, the plan id, the membership id and metadata.

5. Tell me how to use the sandbox (sandbox-api.whop.com) end to end: test
   cards, and whether sandbox webhooks and plans are separate from live ones.

6. Finally: what I must complete before I can receive payouts as an
   individual (no registered company), and what your fee is on each sale.
```

---

## Ek B — Stripe'a geçiş

Şirket kurulduğunda:

1. Stripe'ta aynı 7 fiyatı oluştur, `STRIPE_PRICE_*` değişkenlerini gir.
2. `https://api2.museforge.studio/api/stripe-webhook` için webhook aç
   (`checkout.session.completed`, `invoice.paid`,
   `customer.subscription.deleted`), `STRIPE_WEBHOOK_SECRET`'ı gir.
3. `PAYMENT_PROVIDER=stripe`, redeploy.
4. Whop aboneliklerini **kapatma** — mevcut aboneler Whop'tan yenilenmeye
   devam eder ve `/api/whop-webhook` açık kaldığı sürece kredileri yazılır.
   Yeni satışlar Stripe'a gider. İki taraf aynı `billing.py` tablosunu
   okuduğu için kimse farklı kredi almaz.

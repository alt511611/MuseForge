// The optional location-photo field on the idea form. These keys were used by
// <IdeaForm> but never added to a dictionary, so the live form printed the raw
// key names ("form_location_label") in every language — t() returns the key on
// a miss, which is truthy, so the `|| "…"` fallbacks in the component never ran.
export default {
  en: {
    form_location_label: 'Location Photo',
    form_location_desc: 'Upload one and every scene plays out there. Skip it and the script’s location is generated once, then held the same across all scenes.',
    form_location_upload_btn: 'Upload location photo',
  },
  tr: {
    form_location_label: 'Mekân Fotoğrafı',
    form_location_desc: 'Yüklerseniz her sahne bu mekânda geçer. Yüklemezseniz senaryonun mekânı bir kez üretilip tüm sahnelerde aynı kalır.',
    form_location_upload_btn: 'Mekân fotoğrafı yükle',
  },
  es: {
    form_location_label: 'Foto de la Localización',
    form_location_desc: 'Si subes una, todas las escenas ocurren ahí. Si no, la localización del guion se genera una vez y se mantiene igual en todas las escenas.',
    form_location_upload_btn: 'Subir foto de la localización',
  },
  fr: {
    form_location_label: 'Photo du Lieu',
    form_location_desc: 'Si vous en ajoutez une, toutes les scènes s’y déroulent. Sinon, le lieu du scénario est généré une fois puis conservé identique dans toutes les scènes.',
    form_location_upload_btn: 'Importer une photo du lieu',
  },
  de: {
    form_location_label: 'Location-Foto',
    form_location_desc: 'Mit Foto spielt jede Szene an diesem Ort. Ohne Foto wird die Location des Drehbuchs einmal generiert und bleibt dann in allen Szenen gleich.',
    form_location_upload_btn: 'Location-Foto hochladen',
  },
  pt: {
    form_location_label: 'Foto da Locação',
    form_location_desc: 'Se enviar uma, todas as cenas acontecem ali. Se não, a locação do roteiro é gerada uma vez e mantida igual em todas as cenas.',
    form_location_upload_btn: 'Enviar foto da locação',
  },
  it: {
    form_location_label: 'Foto della Location',
    form_location_desc: 'Se ne carichi una, ogni scena si svolge lì. Altrimenti la location della sceneggiatura viene generata una volta e resta identica in tutte le scene.',
    form_location_upload_btn: 'Carica foto della location',
  },
  nl: {
    form_location_label: 'Locatiefoto',
    form_location_desc: 'Upload er een en elke scène speelt zich daar af. Doe je dat niet, dan wordt de locatie van het script één keer gegenereerd en in alle scènes gelijk gehouden.',
    form_location_upload_btn: 'Locatiefoto uploaden',
  },
  pl: {
    form_location_label: 'Zdjęcie Lokacji',
    form_location_desc: 'Jeśli je dodasz, każda scena rozegra się w tym miejscu. Jeśli nie, lokacja ze scenariusza zostanie wygenerowana raz i pozostanie taka sama we wszystkich scenach.',
    form_location_upload_btn: 'Prześlij zdjęcie lokacji',
  },
  uk: {
    form_location_label: 'Фото локації',
    form_location_desc: 'Якщо завантажите, кожна сцена відбуватиметься там. Якщо ні — локацію сценарію згенерують один раз і збережуть однаковою в усіх сценах.',
    form_location_upload_btn: 'Завантажити фото локації',
  },
  ro: {
    form_location_label: 'Fotografia Locației',
    form_location_desc: 'Dacă încarci una, fiecare scenă se petrece acolo. Dacă nu, locația din scenariu e generată o dată și rămâne aceeași în toate scenele.',
    form_location_upload_btn: 'Încarcă fotografia locației',
  },
  ru: {
    form_location_label: 'Фото локации',
    form_location_desc: 'Если загрузите, все сцены пройдут там. Если нет — локация сценария создаётся один раз и остаётся одинаковой во всех сценах.',
    form_location_upload_btn: 'Загрузить фото локации',
  },
  ar: {
    form_location_label: 'صورة الموقع',
    form_location_desc: 'إذا رفعت صورة، ستدور كل المشاهد في هذا الموقع. وإن لم تفعل، يُولَّد موقع السيناريو مرة واحدة ويبقى نفسه في كل المشاهد.',
    form_location_upload_btn: 'ارفع صورة الموقع',
  },
  hi: {
    form_location_label: 'लोकेशन फ़ोटो',
    form_location_desc: 'फ़ोटो अपलोड करें तो हर सीन वहीं होगा। न करें तो स्क्रिप्ट की लोकेशन एक बार बनेगी और सभी सीन में वही रहेगी।',
    form_location_upload_btn: 'लोकेशन फ़ोटो अपलोड करें',
  },
  ja: {
    form_location_label: 'ロケーション写真',
    form_location_desc: 'アップロードすると、すべてのシーンがその場所で展開します。なければ脚本のロケーションを一度生成し、全シーンで同じに保ちます。',
    form_location_upload_btn: 'ロケーション写真をアップロード',
  },
  ko: {
    form_location_label: '장소 사진',
    form_location_desc: '사진을 올리면 모든 장면이 그곳에서 진행됩니다. 올리지 않으면 각본의 장소를 한 번 생성해 모든 장면에서 동일하게 유지합니다.',
    form_location_upload_btn: '장소 사진 업로드',
  },
  zh: {
    form_location_label: '场景照片',
    form_location_desc: '上传后每个镜头都在该地点发生。不上传则由剧本生成一次场景，并在所有镜头中保持一致。',
    form_location_upload_btn: '上传场景照片',
  },
  id: {
    form_location_label: 'Foto Lokasi',
    form_location_desc: 'Kalau kamu unggah, semua adegan terjadi di sana. Kalau tidak, lokasi dari naskah dibuat sekali lalu dipertahankan sama di seluruh adegan.',
    form_location_upload_btn: 'Unggah foto lokasi',
  },
  vi: {
    form_location_label: 'Ảnh Bối Cảnh',
    form_location_desc: 'Nếu bạn tải lên, mọi cảnh sẽ diễn ra ở đó. Nếu không, bối cảnh trong kịch bản được tạo một lần và giữ nguyên trong tất cả các cảnh.',
    form_location_upload_btn: 'Tải ảnh bối cảnh',
  },
  th: {
    form_location_label: 'ภาพสถานที่',
    form_location_desc: 'ถ้าอัปโหลด ทุกฉากจะเกิดขึ้นที่นั่น ถ้าไม่ ระบบจะสร้างสถานที่จากบทหนึ่งครั้งแล้วคงไว้เหมือนกันทุกฉาก',
    form_location_upload_btn: 'อัปโหลดภาพสถานที่',
  },
};

export default {
  title: "Aklınızdaki planı veren bir metin-videoya istemi nasıl yazılır",
  description:
    "Video istemi, fiil eklenmiş bir görsel istemi değildir. Bir planın kamerası, öznesi, aksiyonu, ışığı ve süresi vardır — ve bunları hangi sırayla söylediğiniz çıktıyı değiştirir.",
  blocks: [
    {
      t: "tldr",
      items: [
        "Video istemi bir resmi değil **bir planı** tarif eder: çerçeve, özne, aksiyon, ışık, objektif, ton — kabaca bu sırayla.",
        "Çerçeveyi en başa koyun. Modelin en çok dikkate aldığı ve sonucu en çok değiştiren cümle odur.",
        "Plan başına tek aksiyon. Tek istemde iki fiil, ikisini de doğru dürüst yapmayan bir klip üretir.",
        "Karede **olanı** tarif edin, olmayanı asla — olumsuzlama verebileceğiniz en güvenilmez talimattır.",
        "Sahne boyunca sabit cümleleri harfi harfine aynı tutun ki ışık ve kostüm kaymasın.",
      ],
    },
    {
      t: "p",
      text: "Kötü yapay zekâ videosunun çoğu, aslında gayet iyi bir fotoğraf üretecek bir istemden çıkar. \"Mutfakta bir kadın, sinematik, 4k, güzel ışık\" bir fotoğrafı tarif eder. Bir planın ayrıca kameranın nerede olduğunu, ne olduğunu ve ne kadar sürdüğünü de söylemesi gerekir — bunları söylemediğinizde model seçer ve mevcut en ortalama seçeneği seçer.",
    },

    { t: "h2", text: "Bir planın altı cümlesi" },
    {
      t: "p",
      text: "Güvenilir bir istemin her seferinde aynı iskeleti vardır. Altı yuvayı doldurun, modelin tahmin edeceği önemli bir şey kalmasın.",
    },
    {
      t: "keyfacts",
      items: [
        { term: "1. Çerçeve", value: "Genel, bel, yakın, omuz üstü — ve öznenin karedeki yeri. En başa yazın." },
        { term: "2. Özne", value: "Kim, ne giyiyor. Sahnenin her planında birebir aynı ifade." },
        { term: "3. Aksiyon", value: "Tek fiil. İlk kare ile son kare arasında ne değişiyor." },
        { term: "4. Kamera", value: "Sabit, yavaş içeri kaydırma, elde, sola pan. \"Sinematik\" bir kamera hareketi değildir." },
        { term: "5. Işık", value: "Kaynak, yön, nitelik — \"soldan alçak pencere ışığı, yumuşak\". Görüntüyü render değil çekim gibi gösteren cümle budur." },
        { term: "6. Ton / renk", value: "Renk işlemi. En sonda, çünkü modelin yeniden yorumlamasında sakınca olmayan tek cümle odur." },
      ],
    },
    {
      t: "p",
      text: "Açık yazıldığında: *\"Bel plan, mutfak tezgâhında antrasit yün palto giymiş bir kadın, kupayı bırakıp kapıya bakıyor, kamera sabit, soldan alçak pencere ışığı, yumuşak, soğuk ve mat renk.\"* Şiirsel değil. Belirsizliği yok — bir istemin ihtiyaç duyduğu tek nitelik de bu.",
    },

    { t: "h2", text: "Çıktıyı en çok değiştiren kurallar" },
    { t: "h3", text: "Plan başına tek aksiyon" },
    {
      t: "p",
      text: "\"İçeri giriyor, paltosunu çıkarıyor ve oturuyor\" size üç şeyin de yarım kaldığı üç saniye verir. Video modelleri klibin süresini istediğiniz her şeye böler. Tek şey isteyin, klibin tamamı ona gitsin.",
    },
    { t: "h3", text: "Yokluğu asla tarif etmeyin" },
    {
      t: "p",
      text: "\"Odada başka kimse yok\" odaya güvenilir biçimde başka insanlar koyar. İstem, çizilecek şeyin tarifidir ve içindeki her isim görünmeye adaydır. Boş odayı olumlu tarif edin: \"boş bir mutfak, geriye itilmiş tek sandalye.\"",
    },
    { t: "h3", text: "Bakışın nereye gittiğini söyleyin" },
    {
      t: "p",
      text: "Aksi söylenmedikçe üretilen oyuncular objektife bakar. Bir dramada bu her planda yanlıştır. Her isteme bir bakış yönü ekleyin — \"kare dışında solda, görünmeyen birine bakıyor\" — görüntü o zaman hareket eden bir portre değil, bir sahne gibi okunmaya başlar.",
    },
    { t: "h3", text: "Sabit cümleleri birebir tekrarlayın" },
    {
      t: "p",
      text: "Bir sahne içinde özne cümlesi, ışık cümlesi ve renk cümlesi planlar arasında karakter karakter kopyalanmalı. Üçüncü planda \"soldan alçak pencere ışığı\"nı \"yumuşak sabah ışığı\" diye yeniden yazmak güneşi yerinden oynatmaya yeter. Planlar arasında değişmesi gereken tek şey çerçeve ve aksiyondur.",
    },
    {
      t: "callout",
      tone: "tip",
      title: "Kalite kelimeleri çoğunlukla süs",
      text: "\"4k\", \"masterpiece\", \"ödüllü\", \"çok detaylı\" güncel video modellerinde çok az iş görür ve iş gören cümlelerin yerini kaplar. Belirli bir objektif ve belirli bir ışık, bir yığın kalite sıfatını her seferinde yener.",
    },

    { t: "h2", text: "Önce ve sonra" },
    {
      t: "table",
      caption: "Aynı plan: belirsiz istemle ve plan olarak yazılmış istemle.",
      head: ["Belirsiz", "Belirli", "Ne değişiyor"],
      rows: [
        ["Ofiste bir dedektif, sinematik", "Bel plan, masada gri paltolu bir dedektif, bir fotoğrafı ters çeviriyor, kamera sabit, sağdan sert masa lambası, noir renk", "Çerçeve, aksiyon ve ışık örneklenmek yerine sizin tarafınızdan seçilir"],
        ["Tepki veriyor, dramatik", "Yakın plan, yüzü, nefesinin ortasında duruyor ve kare dışında sola bakıyor, kamera yavaşça içeri kayıyor, aynı masa lambası sağdan", "Belirsiz bir duygu yerine okunabilir bir an"],
        ["Şehrin güzel bir genel planı", "Genel plan, gece yağmurla ıslanmış sokak, karşı kaldırımdan, su birikintisine yansıyan neon tabela, kamera sabit, yalnızca mekânın kendi ışığı", "Stok kartpostal yerine coğrafyası olan bir yer"],
      ],
    },

    { t: "h2", text: "En-boy oranı istemin parçasıdır" },
    {
      t: "p",
      text: "16:9 için kurulmuş bir plan 9:16'ya kırpılmaya dayanmaz — kırpma karenin ortasını alır ve iyi kurulmuş bir genel planda orta, iki kişinin arasındaki boşluktur. Teslim oranına üretimden önce karar verin ve ona göre kurun. İkisi de gerekiyorsa geniş olan için üretip, karenin merkezine göre değil öznenin konumuna göre kırpın.",
    },

    { t: "h2", text: "İstemin yetmediği yer" },
    {
      t: "p",
      text: "Tek başına istem yazmanın bir tavanı var ve tam olarak tutarlılığın başladığı yerde. Ne kadar disiplinli cümle kurarsanız kurun altıncı planın yüzü birinciyle eşleşmez, çünkü bu bir istem problemi değil, bir **durum** problemidir; çözümü daha iyi kelimeler değil referans görseldir. Ayrıntısı [karakterler neden kayar](/blog/ai-video-character-consistency) yazısında.",
    },
    {
      t: "p",
      text: "Bu, bir hattın sizin yerinize üstlenebileceği kısım da. MuseForge her kare istemini sahnenin kendi kilitlerinden — oyuncu kartı, ışık, yönetmen ön ayarı — kurar; yani değişmemesi gereken cümleler plan başına yeniden yazılmaz, dolayısıyla kayamaz.",
    },

    {
      t: "faq",
      items: [
        {
          q: "Metin-videoya istemi ne kadar uzun olmalı?",
          a: "Altı yuvayı — çerçeve, özne, aksiyon, kamera, ışık, ton — dolduracak kadar uzun, daha fazlası değil. Pratikte bir ilâ üç cümle. Yaklaşık altmış kelimeyi aşan istemlerin sonraki cümleleri göz ardı edilme eğilimindedir, o yüzden bütçeyi sıfatlara değil belirginliğe harcayın.",
        },
        {
          q: "Video modellerinde negatif istem işe yarar mı?",
          a: "Bazı araçlarda ayrı bir negatif istem alanı vardır ve orada ölçülü bir etkisi olur. Ana istemin içine yazılan olumsuzlama — \"araba yok, gülümsemiyor\" — kötü çalışır ve sıklıkla dışladığınız şeyi üretir. Bunun yerine istediğiniz sahneyi olumlu tarif edin.",
        },
        {
          q: "Yapay zekâ videomda neden herkes kameraya bakıyor?",
          a: "Çünkü üretilen bir karede öznenin varsayılanı budur ve tipik bir istemde bunu çürüten hiçbir şey yoktur. Her plana açık bir bakış yönü ekleyin: karakter kime ya da neye bakıyor ve bu, karenin hangi tarafında.",
        },
        {
          q: "Kamera hareketini istemin başına mı sonuna mı yazmalıyım?",
          a: "Aksiyondan sonra, ışıktan önce. Çerçeve en başa aittir çünkü en güçlü dikkate alınan cümledir; ortadaki kamera hareketi ise özne tarifini bastırmadan güvenilir biçimde okunur.",
        },
        {
          q: "İsteme '4k' ya da 'sinematik' eklemek kaliteyi artırır mı?",
          a: "Neredeyse hiç, üstelik istem alanından yer götürür. Adı konmuş bir objektif, adı konmuş bir ışık kaynağı ve adı konmuş bir renk işlemi görüntüyü genel kalite kelimelerinden çok daha fazla değiştirir.",
        },
        {
          q: "Karakterimin kıyafeti neden planlar arasında değişiyor?",
          a: "Çünkü kostüm cümlesi yeniden yazıldı. Referans görsel yüzü kıyafetten çok daha güçlü tutar, bu yüzden giysinin sahnenin her planında birebir aynı ifadeyle tekrar belirtilmesi gerekir.",
        },
      ],
    },

    {
      t: "cta",
      title: "Cümleleri hat kursun",
      text: "MuseForge her kare istemini sahnenin kilitli kadrosundan, ışığından ve yönetmen ön ayarından kurar — aynı kalması gereken kısımlar aynı kalır.",
      button: "Çalışırken görün",
      href: "/",
    },
  ],
};

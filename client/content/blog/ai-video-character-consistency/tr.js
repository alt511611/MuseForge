export default {
  title: "Yapay zekâ videolarında karakterler neden her planda değişir — ve nasıl sabitlenir",
  description:
    "İkinci sahnede değişen bir yüz, yapay zekâ ile yapılmış kısa filmlerin sahte durmasının bir numaralı sebebi. Kaymanın gerçek nedeni ve onu gerçekten durduran dört teknik.",
  blocks: [
    {
      t: "tldr",
      items: [
        "Karakterler kayar, çünkü çoğu metin-videoya aracı her planı yalnızca yazıdan üretir — bir plandan diğerine yüzü taşıyan hiçbir şey yoktur.",
        "Kişiyi kelimelerle yeniden tarif etmek (\"kahverengi saç, yeşil göz, 30'lu yaşlar\") çözmez: aynı tarifin iki üretimi iki farklı insan verir.",
        "Çözüm **referans görsel**: bir kez üretilir ve sonraki her plana metin olarak değil, **görsel girdi** olarak verilir.",
        "Yüzle birlikte kostümü, ışığı ve objektifi de kilitleyin; yoksa karakter tanınabilir kalır ama etrafındaki dünya kalmaz.",
      ],
    },
    {
      t: "p",
      text: "Üç sahnelik bir hikâye yazıyorsunuz. Birinci sahne harika. İkinci sahnede başkarakterin burnu değişmiş. Üçüncüde kimsenin istemediği bir ceket giymiş ve mutfak başka bir daireye taşınmış. Bu, yapay zekâ videosunun kurucu hatası ve çok belirli bir sebebi var.",
    },

    { t: "h2", text: "Kayma neden oluyor" },
    {
      t: "p",
      text: "Metin-videoya modeli bir örnekleyicidir. Ona *\"otuzlu yaşlarında, kahverengi saçlı, mutfakta duran bir kadın\"* derseniz, otuzlu yaşlarında kahverengi saçlı mutfaktaki kadınlardan oluşan devasa bir uzaydan makul bir örnek döndürür. Tekrar çalıştırın, başka bir örnek alırsınız. Model tutarsız davranmıyor — iki kez sordunuz, iki kez doğru cevap verdi.",
    },
    {
      t: "p",
      text: "Bu döngüde hiçbir şey durum taşımıyor. İkinci plan, birinci planın olduğunu bilmiyor. Filminiz uzadıkça sorunun büyümesinin sebebi bu: kayma birikir ve altıncı planda başladığınız karakterle görsel bir ilişki kalmaz.",
    },
    {
      t: "keyfacts",
      items: [
        { term: "Kök neden", value: "Her plan metinden bağımsız örneklenir; planlar arasında görsel durum taşınmaz." },
        { term: "Çözmeyenler", value: "Daha çok sıfat, daha uzun tarif, karaktere isim vermek, seed sayısını artırmak." },
        { term: "Çözen", value: "Bir kez üretilen referans görselin sonraki her planda görsel girdi olarak kullanılması." },
        { term: "O da kayar", value: "Kostüm, saç, mekân, günün saati, objektif ve renk tonu — her biri kendi kilidini ister." },
        { term: "Birikimli", value: "Kayma plan başına birikir; 6 planlık bir film, 2 planlıktan çok daha fazla bozulur." },
      ],
    },

    { t: "h2", text: "İşe yaramayanlar" },
    {
      t: "p",
      text: "İşe yarayan tekniklerden önce yaramayanlarda net olmak gerekiyor, çünkü hepsi yaygın biçimde tavsiye ediliyor.",
    },
    {
      t: "ul",
      items: [
        "**Daha uzun tarifler.** \"Bir kadın\"dan \"omuz hizasında kestane saçlı, sol kaşının üstünde küçük bir yara izi olan 34 yaşında bir kadın\"a geçmek uzayı daraltır, çökertmez. Bütün bu kelimelere uyan başka bir insan alırsınız.",
        "**Karaktere isim vermek.** \"Selin odaya giriyor\" modele hiçbir şey vermez. Selin'in kim olduğunu bilmiyor.",
        "**Seed sabitlemek.** Sabit seed, *aynı istem* için aynı çıktıyı üretir. Planlarınızın istemleri tanımı gereği farklıdır — farklı aksiyon, farklı çerçeve — yani seed artık yüzü sabitlemez.",
        "**Tek uzun çekim yapmak.** Bu karakteri korur ama bütün kurguyu elinizden alır. Kurgusuz film, film değildir; klip'tir.",
      ],
    },

    { t: "h2", text: "Dört kilit" },
    {
      t: "p",
      text: "Tutarlılık tek bir problem değil, dört problem; yalnızca ilkini çözen film hâlâ yanlış görünür. Şu sırayla çözün.",
    },
    {
      t: "steps",
      name: "Bir karakteri yapay zekâ videosunun her planında nasıl sabitlersiniz",
      description:
        "Karakteri, kostümünü, dünyasını ve kamerayı ilk plandan sonuncuya aynı tutan dört geçiş.",
      totalTime: "PT20M",
      items: [
        {
          name: "Portreyi, herhangi bir plandan önce bir kez üretin",
          text: "Karakterin tek bir temiz referans görselini üretin — nötr ifade, dengeli ışık, önden dörtte üç açı. Bunu bir sahnenin parçası olarak üretmeyin. Dramatik bir plandan çıkarılan portre, o planın ışığını ve ruh hâlini kendisine referans veren bütün gelecek karelere taşır.",
        },
        {
          name: "Portreyi tarif olarak değil, görsel girdi olarak verin",
          text: "Sonraki her plan, portrenin kendisini bir görselden-görsele veya referans görsel girdisiyle almalı. Asıl kilit budur: model artık sıfatlara değil piksellere koşullanmıştır ve pikseller yeniden örneklenmez.",
        },
        {
          name: "Kostümü ve saçı da kilitli tarife yazın",
          text: "Referans görsel yüzü tutar; bir ceketi güvenilir biçimde tutmaz. Kostümü her plan isteminde açıkça belirtin ve ifadeyi planlar arasında harfi harfine aynı tutun — altısında da \"antrasit yün palto, yaka kalkık\", birinde \"gri palto\" değil.",
        },
        {
          name: "Dünyayı kilitleyin: ışık, objektif, renk",
          text: "Bir sahnenin her isteminde ışığın yönünü, objektifi ve renk işlemini tekrarlayın. Odanın ışığı kesmeler arasında sabahtan akşama atlarken tanınabilir kalan bir karakter, tutarlı karakter değil, devamlılık hatası olarak okunur.",
        },
      ],
    },
    {
      t: "callout",
      tone: "tip",
      title: "Portre neden sıkıcı olmalı",
      text: "Dramatik çekilmiş bir referans portre — sert yan ışık, uç açı, yüzün yarısında gölge — modele yüz hakkında daha çok değil, daha az bilgi verir. Yarısı saklıdır. Dengeli, cepheden, sıradan ışık yapabileceğiniz en bilgilendirici portredir.",
    },

    { t: "h2", text: "Elle yapmak ile yapıya gömmek arasındaki fark" },
    {
      t: "p",
      text: "Yukarıdaki her teknik, görsel girdi kabul eden herhangi bir araçta elle yapılabilir: portreyi üretin, kaydedin, her plana ekleyin, kostüm cümlesini her isteme kopyalayın. İşe yarar. Aynı zamanda plan başına dört hata fırsatıdır ve hatayı ancak render'ın parasını ödedikten sonra görürsünüz.",
    },
    {
      t: "p",
      text: "Alternatifi, kilitlerin prosedürel değil yapısal olduğu bir hat. [MuseForge](/) karakter portresini çalışmanın başında bir kez üretip her sahnenin her karesinde otomatik olarak yeniden kullanır, kostüm ve ışık cümlelerini bütün plan listesi boyunca taşır ve ikinci bölümü sipariş ettiğinizde aynı kilitleri korur — yani ikinci bölümün başkarakteri, siz hiçbir şeyi yeniden vermeden birinci bölümdekiyle aynı kişidir.",
    },
    {
      t: "table",
      caption: "Aynı dört kilit: elle uygulandığında ve hat tarafından zorunlu tutulduğunda.",
      head: ["Kilit", "Elle", "Yapısal"],
      rows: [
        ["Yüz", "Portreyi kaydet, her plana ekle", "Bir kez üretilir, her kareye otomatik eklenir"],
        ["Kostüm", "Cümleyi her isteme kopyala", "Oyuncu kartından plan listesine taşınır"],
        ["Işık / objektif", "Her planda tekrarla, tutmasını um", "Sahne başına prodüksiyon kilidi olarak tutulur"],
        ["Bölümler arası", "Her şeyi hatırlayıp yeniden ver", "Kadro ve kilitler diziyle birlikte taşınır"],
      ],
    },

    { t: "h2", text: "Karakterin bilerek değişmesi gerektiğinde" },
    {
      t: "p",
      text: "Kilitlemek, ancak kilidi bilerek kırabiliyorsanız işe yarar. Dördüncü sahnede kırmızı palto giyen bir karakterin paltosu o noktadan sonra kalıcı olmalı — beşinci sahnede kaybolmamalı, birinci sahnede geriye dönük belirmemeli.",
    },
    {
      t: "p",
      text: "Bunun temiz yolu, kilitli referansın kendisini düzenleyip yalnızca değişikliğin sonrasındaki planları yeniden render etmek; her planı yeniden istemleyip şansa bırakmak değil. Tek bir giysiyi değiştirmek için bütün filmi yeniden üretmek, bütçenin kaybolma biçimidir.",
    },

    {
      t: "faq",
      items: [
        {
          q: "Yapay zekâ videolarında karakterler neden sahneler arasında değişiyor?",
          a: "Çünkü her plan kendi metin isteminden bağımsız üretilir ve karakterin görünümünü bir plandan diğerine taşıyan hiçbir şey yoktur. Model her seferinde makul ama yeni bir insan örnekler. Bunu yalnızca sonraki planları karakterin gerçek bir referans görseline koşullamak durdurur.",
        },
        {
          q: "Daha ayrıntılı karakter tarifi tutarlılığı çözer mi?",
          a: "Hayır. Uzun tarif modelin döndürebileceği yüz aralığını daraltır ama hiçbir zaman tek bir yüze indirmez. Aynı ayrıntılı tarifin iki üretimi, tarife uyan iki farklı insan verir.",
        },
        {
          q: "Sabit seed yapay zekâ karakterini tutarlı tutar mı?",
          a: "Bir film boyunca tutmaz. Seed yalnızca birebir aynı istem için aynı çıktıyı yeniden üretir. Bir hikâyedeki her planın istemi farklı olduğundan — farklı aksiyon, çerçeve, replik — istem değişir değişmez seed karakteri sabitlemeyi bırakır.",
        },
        {
          q: "Karakter başına kaç referans görsel gerekiyor?",
          a: "Her yerde kullanılan tek bir iyi görsel, birbirini tutmayan birkaç görselden iyidir. Dengeli ışıklı, önden dörtte üç açılı tek bir portre çoğu hat için yeterlidir; farklı ışıkta ikinci bir referans eklemek modelin çektiği aralığı daraltmak yerine genelde genişletir.",
        },
        {
          q: "Karakter tutarlılığı kıyafeti ve saçı da kapsar mı?",
          a: "Yalnızca kısmen. Referans portre yüz yapısını güçlü, saç modelini orta düzeyde tutar; kıyafeti, özellikle omuzların altında, zayıf tutar. Kostümün her planın isteminde, her seferinde aynı ifadeyle tekrar belirtilmesi gerekir.",
        },
        {
          q: "Sahneler değil, bölümler arası tutarlılık ne olacak?",
          a: "Aynı problemin bir üst seviyesi ve aynı cevabı istiyor: referans portre ve prodüksiyon kilitleri diziyle birlikte saklanmalı ve sonraki bölüme yeniden uygulanmalı. Bunları render sonunda atan bir araç, ikinci bölümde size yeni bir başrol verir.",
        },
      ],
    },

    {
      t: "cta",
      title: "Kilidin çalıştığını görün",
      text: "Demo modu bütün hattı — oyuncu portresi, storyboard, kareler — API anahtarı olmadan ve kredi harcamadan çalıştırır.",
      button: "MuseForge'u ücretsiz deneyin",
      href: "/",
    },
  ],
};

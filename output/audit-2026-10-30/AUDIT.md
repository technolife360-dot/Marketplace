# SentryLoot: raqobatchilar bilan taqqoslash

Tekshiruv: 30-oktabr 2026. Manba: foydalanuvchi Chrome’da ochgan https://game-store-eeg5smxfx-shuxrat4iks-projects.vercel.app/#home .

SentryLoot’ning qora/oltin vizual tizimi, yangi SL belgisi va mahsulot sahifasi yaxshi asos beradi. Hozir savdoga tayyorlik, haqiqiy takliflar va ishonch ma’lumotlarining izchilligi ustuvor. Bu tekshiruv reyting yoki trafik bo‘yicha raqobatchilardan ustunlikni isbotlamaydi.

## Eng muhim topilmalar

| Ustuvorlik | Tasdiqlangan holat | Xaridorga ta’siri | Keyingi ish |
|---|---|---|---|
| P0 | Toza in-app brauzerda gamestorehub.com Vercel login oynasiga yo‘naltirildi. Vercel loyiha API’si ssoProtection.enabled=true, deploymentType=all ekanini tasdiqladi. | Hisobi yo‘q oddiy tashrifchi do‘konni ko‘ra olmaydi. | Production domeni uchun ommaviy kirish siyosatini sozlash; preview va admin himoyasini alohida saqlash. Bu auditda sozlama o‘zgarmadi. |
| P1 | Footer va yordam sahifalari live to‘lovlar/savdolar o‘chiqligini aytmoqda. | To‘liq real xarid yo‘li hali foydalanuvchiga taqdim etilmagan. | To‘lov, webhook, muvaffaqiyatsiz to‘lov, refund, sotuvchi hisob-kitobi va buyurtma yakunlanishini sinovdan o‘tkazib, ruxsatli mahsulotlar uchun ishga tushirish. |
| P1 | Katalog: “Showing 1 of 1 listings”. | 15 o‘yin rasmi ko‘p tanlov bor degan taassurot beradi, lekin faol taklif bitta. | Boshlash uchun 3–5 asosiy yo‘nalishda mavjud, tekshirilgan takliflar yig‘ish. Har o‘yinga 10–20 taklif boshlang‘ich maqsad bo‘lishi mumkin; bu majburiy bozor standarti emas. |
| P1 | Mahsulotning Seller blokida “No reviews yet / 0 sales”; o‘sha do‘kon profilida “5.0 / 1 reviews / 1 completed sales”. | Bir sotuvchining obro‘si turli sahifada zid ko‘rinadi. | Savdo va sotuvchi sharhlarini umumiy ma’lumot manbasidan olish; mahsulot sharhini sotuvchi sharhidan aniq ajratish. |
| P1 | PUBG Top Up’da 11 paketning barchasi “Price not set”; Buy now/Add to cart o‘chiq; xizmat va to‘lov ulanmagani yozilgan. | Sahifa bor, ammo xizmat sotilmayapti. | Supplier, paket mosligi, narx/marja, UID tekshiruvi, order statuslari va qayta urinilganda takroriy yetkazmaslikni tekshirish. Tayyor bo‘lguncha coming-soon holatini bir xil saqlash. |
| P1 | OVR-127 listingida “Rank” va “Transferable” — “Not specified”; region Asia, linked service Apple/iCloud. | Xaridor nimani olishi va akkauntni qanday qabul qilishini yetarli baholay olmaydi. | O‘yinga mos majburiy parametrlar, transfer usuli, bog‘langan xizmatlar, qurilma/hudud talabi va yangi egaga topshirish bosqichlari. “Rank” tegishli bo‘lmasa N/A deb ajratish. |
| P1 | Regional preferences’da konvertatsiya taxminiyligi va to‘lov original valyutada olinishi aytilgan. | Display valyutasi yakuniy yechiladigan valyuta degan noto‘g‘ri kutish bo‘lishi mumkin. | Checkout’da yakuniy valyuta, summa va komissiyani oldindan ko‘rsatish; quote muddati va serverdagi narxni sinash. Haqiqiy checkout bu auditda bajarilmadi. |
| P2 | Purchase blokidagi Order protection qisqa umumiy matn; yordam sahifasi jarayon va yakuniy savdo shartlari hali tayyorlanayotganini aytadi. | Himoya qachon tugashi va nizoda nima bo‘lishi xarid qarori yonida aniq emas. | Buy tugmasi yonida himoya muddati, qamrovi, istisnolari, nizo yo‘li va yordam vaqti; faqat real bajariladigan va’dalar. |
| P2 | Mahsulotda sotuvchi “admin”, do‘kon sarlavhasi “Fc mobile”; tavsif “I want sell account”. | Brend va sotuvchi shaxsi professional, izchil taqdim etilmagan. | Store nomi va sotuvchi nomini moslash, foydali tavsif, real javob vaqti; ishonch belgisi ma’nosini tushuntirish. |
| P2 | Desktop va 390px mobil birinchi ekranida mavjud listingning narxi ko‘rinmaydi; artwork/o‘yin kategoriyalari ustun. | Sotilayotgan aniq taklifga yetish uchun ko‘proq scroll kerak. | Hero’ni mavjud kampaniya yoki real taklifga bog‘lash; real mahsulot va narx blokini yuqoriroqda berish. |
| P2 | Bo‘sh savat markazida qora panel, tashqarisi boshqa to‘q fon; CTA oddiy matnli link. | Oldingi “bitta asosiy background” talabi barcha sahifada izchil emas; bo‘sh holat kuchsiz. | Bir xil fon tokeni va aniq “Browse listings” tugmasi; faqat mavjud mahsulotlardan qaytish yo‘li. |

## Raqobatchilardan olinadigan aniq mezonlar

| Mezoni | Raqobatchidagi dalil | SentryLoot uchun qo‘llash |
|---|---|---|
| Sotuvchi ishonchi | [G2G rasmiy qo‘llanmasi](https://help.g2g.com/en/articles/10000079-how-do-i-know-if-a-seller-is-trustworthy) seller rank, yakunlangan buyurtmalar va buyer rating’ni birga baholashni tushuntiradi. | Hozirgi 0/1 tafovutini yo‘qotish; real savdo, sharh, javob va yetkazish ma’lumotini izchil ko‘rsatish. |
| Himoya jarayoni | [Eldorado qo‘llanmasi](https://support.eldorado.gg/en/articles/17098994-good-to-know-before-you-buy) to‘lov qachon ushlab turilishi, tekshirish va nizo bosqichlarini bayon qiladi. | SentryLoot’ning o‘z real operatsion qoidalarini qisqa, aniq tushuntirish; raqib muddatlarini avtomatik ko‘chirmaslik. |
| Hududga moslik | [Eneba rasmiy qo‘llanmasi](https://www.eneba.com/gb/support/article/product-key-activation-country) mamlakat bo‘yicha faollashtirish mosligini va istisnolarni mahsulot sahifasida ko‘rsatishini aytadi. | Valyuta almashtirishdan tashqari, mahsulotning tanlangan davlat va platformaga mosligini xarid oldida tushuntirish. |
| Mahsulot topish | [Eldorado bosh sahifasi](https://www.eldorado.gg/) kategoriya, real taklif, yaqinda ko‘rilganlar va narx bloklarini ko‘rsatadi. [Eneba](https://www.eneba.com/) kampaniya va mahsulot turiga qarab bo‘limlar beradi. | Mavjud assortimentdan kelib chiqadigan bo‘limlar; bo‘sh kategoriyani kuchli reklama qilmaslik. |

Eldorado va Eneba bosh sahifalari Chrome’da ko‘rildi. G2G bo‘yicha xulosalar rasmiy ochiq qo‘llanmaga tayangan; uning to‘lov jarayoni brauzerda sinovdan o‘tkazilmadi. Eneba kalit/gift-card yo‘nalishi bilan farq qiladi; undan region va mahsulot topish mezoni olindi.

## Allaqachon mavjud imkoniyatlar

Mahsulotning 3 rasmli galereyasi, qoldiq, narx, 15 daqiqalik yetkazish ko‘rsatkichi, sotuvchi profili, wishlist, saved searches, narx kuzatish, region/valyuta oynasi, kupon va bonus interfeysi, review va yordam/nizo sahifalari bor. Mavjudlik ularning barcha real savdo holatlarida to‘g‘ri ishlashi tasdiqlandi degani emas. Ularni qayta yaratishdan oldin yakuniy xarid yo‘li bo‘yicha tekshirish kerak.

## Ekranlar bo‘yicha tekshiruv

### 1. Bosh sahifa — vizual asos yaxshi, aniq savdo taklifi sust

Yangi logo, oltin aksent, o‘qiladigan sarlavha va bosh CTA ko‘rinadi. Birinchi ekranda real narx va mavjud listing yo‘q. Katta o‘yin rasmlari katalogdagi haqiqiy mavjudlik bilan bog‘lanishi kerak.

![1. Bosh sahifa](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/01-home.png)

### 2. Katalog — eng katta kamchilik assortiment

1 ta taklif. Saved searches va filtrlar bor. Bo‘sh maydon va tanlov yetishmasligi ko‘rinadi. 4 ustunli dizaynni bir mahsulot bilan mazmunli baholab bo‘lmaydi.

![2. Katalog](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/02-catalogue.png)

### 3. Mahsulot — xarid bloki aniq, ma’lumot va ishonch yetishmaydi

OVR-127 sarlavhasi ko‘rilgan asosiy rasmdagi OVR-127 bilan mos. Bu tekshiruvda eski OVR tafovuti qayta topilmadi. Narx, qoldiq va galereya bor; sotuvchi blokidagi statistika do‘kon bilan mos emas. “Message seller” hozirgi sessiyada o‘chiq, lekin sessiya listing egasiga tegishli bo‘lgani uchun buni mustaqil xato deb belgilamadim.

![3. Mahsulot](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/03-listing.png)

### 4. Sotuvchi — statistika ko‘rsatiladi, boshqa sahifalar bilan ziddiyat bor

Profil 5.0, 1 sharh, 1 completed sale ko‘rsatdi. Sharhning haqiqiy/live yoki test kelib chiqishi tekshirilmagan. Test savdolar va sharhlar bo‘lsa, ularni real savdo dalili sifatida aralashtirmaslik kerak.

![4. Sotuvchi](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/04-store.png)

### 5. Top Up — xaridga ochilmagan

11 ta narxsiz PUBG paketi va o‘chiq xarid tugmalari. UID xavfsizligi haqida foydali tushuntirish bor. Supplier orqali haqiqiy yetkazish sinovi bajarilmadi.

![5. Top Up](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/05-topup.png)

### 6. Savat — bo‘sh holat ishlaydi, checkout tekshirilmagan

Savat bo‘sh. Uni to‘ldirmadim, buyurtma yaratmadim, pul yechmadim. Footer’da live payments disabled yozuvi bor. Checkout, refund va bonus ledger’ning real ishlashi haqida bu ko‘rinishdan hukm chiqarib bo‘lmaydi.

![6. Savat](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/06-cart.png)

### 7. Mobil bosh sahifa — 390×844 da sig‘adi, narx pastda

Ko‘rilgan holatda gorizontal overflow yo‘q. Logo, hero va menyu joylashgan. Real listingning narxi birinchi ekran ostida. Tezlik, real telefon GPU/FPS va barcha mobil sahifalar o‘lchanmadi.

![7. Mobil](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/07-mobile-home.png)

### 8. Yordam — tuzilma bor, yakuniy savdo shartlari ochilmagan

Help’da order, nizo, region va akkaunt xavfsizligi bo‘limlari bor. Sahifa live savdolar o‘chiqligi, test yozuvlar haqiqiy savdo emasligi va kompaniya/final shartlar launch oldidan berilishini aytadi.

![8. Yordam](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/10-order-help.png)

## Raqobatchi ekranlari

Eldorado: aniq kampaniya, kategoriya navigatsiyasi va real taklif bloklari. Uning himoya va 24/7 support bayonotlari raqibning o‘z va’dalari; bu audit uning xizmat sifatini mustaqil tasdiqlamaydi.

![Eldorado](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/08-eldorado.png)

Eneba: kategoriya, kampaniya, mahalliy valyuta va savdo bo‘limlari; cookie oynasi ham ushbu joriy tashrifning bir qismi sifatida ko‘rinadi.

![Eneba](/Users/technolifeno360chettel889563333/Desktop/marketplace/output/audit-2026-10-30/09-eneba.png)

## Bajarish ketma-ketligi

1. Ommaviy production kirishini ochish, preview/admin himoyasini saqlash.
2. Sotuvchi statistikasidagi tafovutni tuzatish va mahsulot transfer ma’lumotlarini to‘ldirish.
3. Ruxsatli mahsulotlar uchun to‘lov → yetkazish → tasdiqlash → bonus → refund yo‘lini boshidan oxirigacha sinash.
4. Supplier tanlab Top Up narx va yetkazishini sinash; faqat tayyor paketlarni sotuvga ochish.
5. Mavjud, tekshirilgan katalogni shakllantirish va real sharhlarni izchil ko‘rsatish.
6. Region mosligi va yakuniy to‘lov summasini aniqlashtirish.
7. Bosh sahifani real takliflarga yaqinlashtirish, fon va bo‘sh holatlarni birlashtirish.
8. Real telefonlarda tezlik, klaviatura/fokus, reduced-motion va tarjimalar bo‘yicha alohida tekshiruv.

Qo‘shimcha animatsiya yuqoridagi kamchiliklarni hal qilmaydi. Avval mavjud animatsiyalar ishlaganda xarid qilish osonligini va harakatni kamaytirish sozlamasiga mosligini o‘lchash kerak.

## Tekshiruv chegaralari

Bu xavfsizlik penetration testi, to‘liq accessibility sertifikatsiyasi yoki moliyaviy audit emas. Klaviatura bo‘yicha to‘liq yo‘l, ekran o‘quvchi, barcha 14 til, email yetib borishi, haqiqiy refund/payout, chargeback, live supplier, analytics konversiyasi va Core Web Vitals tekshirilmadi. Ularni yo‘q yoki buzilgan deb belgilamadim. Kod, real buyurtma, to‘lov va production sozlamalari o‘zgartirilmadi. Faqat audit hisobotlari saqlandi; Chrome’dagi foydalanuvchi sahifasi Home’ga qaytarildi.

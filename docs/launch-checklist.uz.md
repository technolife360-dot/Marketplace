# Ishga tayyorgarlik: 37 bandning holati

2026-10-21. Bu hujjat funksiyaning yozilgani bilan productionda amalda tasdiqlanganini ajratadi. Payment va supplier Top Up API ulanmagan. Haqiqiy mahsulot, biznes rekvizitlari, ish jadvali va xodimlar foydalanuvchi tomonidan hali tayyorlanmagan.

1. **Real katalog:** mavjud admin va sotuvchi shakllari saqlangan; tayyorgarlik tekshiruvi qo‘shildi. Haqiqiy nom/narx/qoldiq/rasm kelmaguncha katalog to‘ldirilgani deb hisoblanmaydi.
2. **Test e’lonlari:** production katalog, o‘xshash takliflar, sitemap va ommaviy detaildan ajratildi. Egasi/admin tekshira oladi.
3. **Sotilgan karta:** qoldiqsiz mahsulotlarda Sold out belgisi bir xil qo‘llanadi.
4. **Ma’lumot sifati:** faqat raqamli buyum nomi va active kabi variant qiymatlari tekshiruvga tushadi; moderatorga tuzatish sabablari ko‘rsatiladi. Mazmunning to‘g‘riligini moderator tasdiqlashi kerak.
5. **Bo‘sh katalog:** filtrni tozalash, qidiruvni saqlash va sotishni boshlash amallari bor.
6. **Offers nomi:** narx saralashi Lowest prices / tegishli UZ-RU tarjimalari bilan nomlandi.
7. **Tillar:** yangi oynalar va footer UZ/RU/EN, email hisob tiliga mos. Barcha eski matnlarning to‘liq inson tahriri hali alohida tekshiruv talab qiladi.
8. **Yordam nomi:** server metadata va brauzerda Help center bir xil.
9. **Support jadvali:** admin draft shakli, vaqt mintaqasi, mas’ul, javob muddati va nashr oldi tekshiruvi bor. Haqiqiy jadval berilmagan; avtomatik 24/7 va’dasi qo‘yilmaydi.
10. **Savdo shartlari:** biznes, aloqa, himoya qamrovi va istisnolarni tayyorlash/nashr qilish shakli bor. Yakuniy biznes ma’lumoti va siyosat tasdig‘i kutiladi: launch-business-draft.uz.md.
11. **Top Up saqlanganlari:** paketlar hisobga bog‘langan; qayta ochilganda saqlanadi. Brauzerda 60 UC/325 UC alohidaligi tekshirildi.
12. **Paketlar manbasi:** admin nom/rasm/tarkibni boshqaradi; API, galereya va tanlov bir manbadan oladi. Haqiqiy narx va supplier ulash keyin.
13. **Coming soon:** rozilik bilan ishga tushish xabariga yozilish saqlanadi. Haqiqiy xizmat ochilmaganligi sabab launch xabari yuborilmadi; real ochilish e’loni hali operator amali.
14. **O‘xshash takliflar:** taklif yo‘qligi tushunarli matn bilan ko‘rsatiladi.
15. **Sotuvchi tayyorgarligi:** profil va mahsulot sifatidagi yetishmovchiliklar /api/seller/readiness orqali, mavjud boshqaruvda ko‘rsatiladi.
16. **Sotuvchi darajasi:** haqiqiy yakunlangan savdolar va sharhlardan hisoblanadi; sandbox kirmaydi, mezonlar ochiq.
17. **Miqdor narxlari:** egasi belgilaydigan 5 tagacha bosqich; katalog/detail, savatcha va checkout bir xil narxdan foydalanadi; rezervda o‘zgartirish yopiq.
18. **Xodim ruxsatlari:** support/moderation/content alohida; full admin parol va mavjud MFA bilan beradi. Scoped staff moliyaviy/admin imkoniyatlariga kira olmaydi. Production xodimlari hali tayinlanmagan.
19. **Xizmat bosqichlari:** sotuvchi reja belgilaydi, order snapshot saqlaydi, topshirish/tasdiq/tuzatish ketma-ket; kelishilgan barcha bosqichlar qabul qilinmasdan yakunlash yopiq. Bosqichning o‘zi pul chiqarmaydi.
20. **Video dalil:** maxfiy MP4, 4 MiB/30 soniya, qayta kodlash, ovoz/metadata olib tashlash, ruxsat va retention mavjud; haqiqiy video bilan lokal sinov o‘tdi. Production R2 upload end-to-end yangi deploydan keyin tasdiqlanishi kerak.
21. **Fon Web Push:** consent, shifrlangan subscriptions, service worker, provider yuborish, o‘chirish, umumiy maxfiy matn, dedup va cheklangan batch bor. Vercel/GitHub push-only token va WEB_PUSH_ENABLED sozlandi. Deploy va rozilik bergan haqiqiy qurilmada yetib kelishi hali tasdiqlanmagan.
22. **Ma’lumot nusxasi:** parol/MFA bilan xavfsiz export; sessiya kaliti, parol hash va maxfiy topshirish ma’lumoti kirmaydi.
23. **Rasmli yordam:** mahsulot/order/support jarayoni uchun javobga yo‘naltirilgan vizual qadamlar va misollar qo‘shildi. Haqiqiy operator qo‘llanmasi uning tasdiqlangan tartibiga mos tahrir qilinadi.
24. **Murakkab order:** mavjud regression suite va yangi bosqich testlari ketma-ketlik, egalik, snapshot, limit va sandbox holatlarini tekshiradi. Productionda real pul ishlatilmagan.
25. **Telefonlar:** responsive brauzer tekshiruvi bor; haqiqiy iPhone/Safari va Android/Chrome sinovi bajarildi deb da’vo qilinmaydi. device-acceptance.uz.md bo‘yicha qurilma kerak.
26. **Uzilishlar:** mavjud retry/idempotency regression testlari saqlangan. Haqiqiy telefon interneti uzilishi, sessiya tugashi va ikki qurilma qabul sinovi hali kerak.
27. **Mobil tezlik:** production Core Web Vitals o‘lchovi olinmadi. web-perf skill talab qilgan Chrome DevTools MCP yo‘q; sonlar uydirilmadi.
28. **Yuklama:** scripts/qa_local_load.py izolyatsiyalangan bazada 8 parallel foydalanuvchi/104 so‘rov, 0 xato. Bu production sig‘imi bo‘yicha kafolat emas.
29. **Monitoring:** mavjud health/workflow saqlangan; API request ID, anonim route/status/duration loglari va DB ulanish xatosida JSON 503 qo‘shildi. Xato ataylab productionga kiritilmadi; real upload/login alert yo‘lini alohida operator drill bilan yakunlash kerak.
30. **Email kelishi:** UZ/RU/EN shablon va transport testlari bor. Inbox/Spamga haqiqiy yetib kelishi bu ishda tekshirilmagan.
31. **Tiklash:** GitHub backup/restore rehearsal 39464206794 success. Bu barcha production media va ilova kalitlari bilan to‘liq disaster recovery drill bo‘ldi degani emas.
32. **2FA:** mavjud MFA regression va reauth tekshiruvlari saqlangan; production muhim hisoblarida egasi yoqishi va recovery kodini o‘zi tekshirishi kerak.
33. **SEO:** testlar sitemapdan chiqarildi; savdo yopiq production preview noindex/nofollow, robots Disallow /. Real katalog ochilgach indekslashni qayta tekshirish kerak.
34. **Accessibility:** yangi formalar label/focus/error, modal va 44px tugma qoidalariga moslandi. Telefon ekran o‘quvchisi bilan to‘liq qabul sinovi hali kerak.
35. **Status sahifasi:** operator tasdiqlagan holat; standart holat “not reported”, uydirma uptime yo‘q. /#service-status.
36. **Inson sinovi/qayta xarid:** amaliy 5–10 ishtirokchi ssenariysi tayyorlandi; real odamlar bilan tadqiqot o‘tkazilmadi. Mavjud orderdan e’lon/do‘konga kirish saqlangan; yo‘q mahsulotni avtomatik qayta buyurtma qilmaydi.
37. **Kupon/referral/loyalty:** sotuvchiga tegishli kupon, muddat/limit/bir xaridor nazorati, checkoutda qayta tekshiruv; o‘zini taklif qilish yopiq; sandboxdan ball yo‘q. Ball pul emas va hozir almashtirilmaydi. Real katalog/to‘lov ochilmaguncha haqiqiy aksiya natijasi mavjud emas.

## Dalillar

- Backend: tests/test_launch_readiness.py, tests/test_push_video.py, tests/test_email_service.py va mavjud to‘liq regression to‘plami.
- Frontend: tests/frontend.test.cjs; npm run build sintaksis tekshiruvi.
- Mahalliy yuklama: 104/104 HTTP 200, median 11.85 ms, p95 160.91 ms (faqat lokal SQLite).
- Backup: https://github.com/technolife360-dot/Marketplace/actions/runs/39464206794
- Tashqi qabul ssenariysi: device-acceptance.uz.md.

Production RLS qayta auditi CLI orqali DATABASE_URL olinmagani sabab yakunlanmadi; sxema auditi tasdiqlandi deb hisoblanmaydi.

Yangi SQL jadval/ustun qo‘shilmadi: mavjud yopiq platform_config va experience_preferences ishlatiladi. Shaxsiy tokenlar, obunalar va biznes draftlari ommaviy APIga chiqmaydi. Productiondagi yakuniy yetib kelish, fizik qurilma va biznes ma’lumotlariga bog‘liq bandlar yuqorida ochiq qayd etilgan.

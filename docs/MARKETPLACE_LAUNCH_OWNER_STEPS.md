# Savdoga tayyorgarlik: egasi bajaradigan qadamlar

2026-10-29. Bu ro‘yxat live savdo ochilganini anglatmaydi.

## Katalog nima?

Katalog — xaridor sotib oladigan **haqiqiy takliflar**: nom, tavsif, haqiqiy rasm, narx, valyuta, mavjud miqdor, platforma, region, yetkazish vaqti va shartlar. O‘yin banneri mahsulot yoki mavjud qoldiq hisoblanmaydi.

1. Avval sotishga vakolatingiz bor 3–5 ta o‘yinni tanlang. Akkaunt savdosiga publisher cheklovi bo‘lsa, uni ruxsat etilgan mahsulot deb hisoblamang.
2. **Sell Item → Seller dashboard** orqali taklif kiriting. Ko‘p mahsulot bo‘lsa, shu sahifadagi CSV namunasini yuklab, haqiqiy ma’lumotlar bilan draft import qiling. Import avtomatik nashr etmaydi.
3. **Admin → Games & catalogue** sahifasida sifat xatolarini ko‘ring; har bir taklifni moderatsiyada tekshiring. Rasm, sarlavha va tavsifdagi level/OVR/miqdor aynan mos bo‘lsin. Hozirgi FC Mobile taklifidagi OVR-126/OVR-127 tafovutini mahsulot egasi tasdiqlashi kerak.
4. Narx va qoldiqni o‘zingiz tasdiqlang. UZS qiymatlari ichki bazada butun so‘m, MYR qiymatlari senlarda saqlanadi; masalan 300 MYR = 30000. CSV importining mavjud UZS formatiga amal qiling; boshqa valyutani importga taxminan yozmang.
5. Faqat haqiqiy yakunlangan buyurtmalar sharh va savdo tarixiga asos bo‘lsin. Sandbox buyurtmalar obro‘ni oshirmaydi.

## Stripe sandbox

Ulangan connector: **SentryLoot sandbox**, test rejimi. Default konfiguratsiyada karta, Apple Pay va Link yoqilgan; FPX, GrabPay va Google Pay mavjud emas. Apple Pay ko‘rinishi mos qurilma va brauzerga bog‘liq. Stripe API orqali Top Up va marketplace parametrlari bilan RM10 dan ikkita unpaid test sessiyasi yaratildi: ikkalasi MYR, karta va Link bilan ochildi. Bu saytdagi webhook yoki yetkazish sinovi emas. Connector sayt serveriga API kalitlarini bermaydi; eski sandbox uchun sozlangan kalit, account ID va webhook signing secret’ni boshqa hisob bilan aralashtirmang.

Serverga sandbox cheklangan kaliti va shu sandbox hisob ID sini deployment secret sifatida kiriting. Kalitlarni chatga yoki Git’ga qo‘ymang:

- `PAYMENT_PROVIDER=stripe_test`
- `STRIPE_TEST_SECRET_KEY` — `rk_test_…` yoki test secret.
- `STRIPE_TEST_ACCOUNT_ID` — aynan tanlangan sandbox hisobi.
- `STRIPE_TEST_WEBHOOK_SECRET` — webhook endpoint signing secret.
- `PUBLIC_BASE_URL` — saytning HTTPS origin’i, path/query’siz.
- Production muhitidagi himoyalangan ichki sinov uchun mavjud `MARKETPLACE_INTERNAL_TESTING_ENABLED=true` alohida talab etiladi. Bu audit uni o‘zgartirmadi.

Sandbox Dashboard’da webhook endpoint sifatida `https://<your-origin>/api/webhooks/stripe-test` ni yarating va `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `checkout.session.async_payment_failed`, `charge.refunded`, `charge.dispute.created` hodisalarini ulang. Endpoint’ning signing secret qiymatini `STRIPE_TEST_WEBHOOK_SECRET` sifatida saqlang. Production `/api/health` hozir `stripe_test`, `internal_testing`, `sales_enabled=false` ko‘rsatdi. Bu sozlamalar borligini bildiradi, payment/webhook E2E tasdig‘i emas. Mahalliy QA’da test secretlari yo‘q; avtomatik testlar imzolangan webhook va SDK javoblarini izolyatsiyada tekshiradi.

Ichki UZS → Stripe minor-unit konvertatsiyasi checkout, webhook, refund va settlement chegaralarida bajariladi. Eski versiyada noto‘g‘ri kichik summa bilan yaratilgan sessiyalar avtomatik yangi charge yaratmaydi: operator ularni sandbox’da tekshirib, reconcile qilishi kerak.

Yangi Checkout sessiyalari buyurtmadagi charge valyutasini saqlaydi. Stripe Dashboard valyuta va xaridorga mos usullarni tanlaydi. Sandbox’da karta muvaffaqiyati, rad etilishi, 3D Secure, checkout bekor qilinishi, webhook takrorlanishi va refund yakunini har bir savdo yo‘lida tekshiring. FPX yoki GrabPay mavjud bo‘lgan hisobda redirect, qaytish va pending refund yakunini ham sinang. Pending refund keyingi ishga tushirishda qayta yaratilmaydi.

## Stripe Malaysia uchun live savdo

1. Stripe arizasida Malayziyada ro‘yxatdan o‘tgan operator, sayt, biznes manzili va bank ma’lumotlaridan foydalaning. **Admin → Team & business profile** orqali tasdiqlangan yuridik nom, ommaviy biznes manzili, aloqa va haqiqiy ish vaqtini e’lon qiling. Bu ma’lumotlar Stripe hisobidagi ma’lumotga mos bo‘lsin. [Stripe Services Agreement](https://stripe.com/legal/ssa), [Stripe sayt talablari](https://support.stripe.com/questions/business-website-for-account-activation-faq).
2. Top Up, o‘yin buyumlari, Steam/gift card va kodlar, akkaunt e’lonlari hamda mustaqil sotuvchilarni alohida ko‘rsating. Stripe’dan qaysi toifa va bozorlarga ruxsat berilganini yozma aniqlashtiring. Top Up uchun supplier/noshir ruxsatini, akkaunt va buyumlar uchun transfer huquqini hujjatlashtiring. [Stripe cheklangan toifalari](https://stripe.com/legal/restricted-businesses).
3. Marketplace uchun Stripe Connect’da Malaysia platformasi va sotuvchilarning aniq mamlakatlari bo‘yicha onboarding, payout va transchegaraviy qamrovni tekshiring. Merchant of record, komissiya, payout jadvali, refund, dispute va salbiy balans uchun mas’uliyatni belgilang. [Stripe Connect marketplace](https://docs.stripe.com/connect/marketplace).
4. `SPIN_WIN_REAL_AWARDS_ENABLED=false` bo‘lsin. Real sovrinli tasodifiy kampaniyani Stripe ishga tushirishidan ajrating va modelni Stripe’ga to‘liq ochiqlang. Avvalgi sovrin va vaucherlarni saqlang, ularni topshirish va ishlatish tartibini Stripe bilan kelishing. Pauza yangi yutuqlarni bloklaydi va oldingi g‘oliblar tarixini saqlaydi.
5. `/terms`, `/privacy-policy`, `/refunds`, `/delivery`, `/disputes`, `/seller-policy`, `/contact` va `/about` sahifalarini tekshiring. Real paket yetkazish muddati, refund va bekor qilish mezonlari va muddatlari, komissiya hamda payout shartlarini ishga tushirishdan oldin operator tasdiqlaydi. Ularni checkout va tegishli mahsulot sahifasida ko‘rsating. [Stripe Website Checklist](https://docs.stripe.com/get-started/checklist/website).
6. Tasdiqlangan qamrov bo‘yicha test adapterdan alohida live adapter, imzolangan webhook, idempotent fulfillment, refund va dispute reconciliation hamda Connect tekshiruvlarini tayyorlang. Checkout’dagi mahsulot, yakuniy summa va charge valyutasi saqlangan buyurtmaga mos bo‘lsin. Saytdagi display currency tanlovi charge yoki settlement valyutasini o‘zi o‘zgartirmaydi. [Checkout fulfillment](https://docs.stripe.com/checkout/fulfillment).
7. [Stripe Payment methods](https://dashboard.stripe.com/settings/payment_methods) orqali tasdiqlangan hisobda karta va mos raqamli hamyonlarni tekshiring. [FPX](https://docs.stripe.com/payments/fpx) va [GrabPay](https://docs.stripe.com/payments/grabpay) Malayziya to‘lovlari uchun MYR talab qiladi. FPX uchun biznes ro‘yxat raqami kerak va u mavjud marketplace’dagi [separate charges and transfers modeliga mos emas](https://support.stripe.com/questions/stripe-product-compatibility-with-fpx). Top Up uchun FPX/GrabPay’ni faqat hisobda usul mavjud bo‘lsa va to‘lov, yetkazish hamda refund sinovlari o‘tgach yoqing. About Us’dagi ro‘yxat Stripe imkoniyatlarini ko‘rsatadi; live qabulni tasdiqlamaydi.

## Top Up supplier hali yo‘q

1. Avval vakolatli supplier bilan hisob/shartnoma va kerakli mamlakatlar/o‘yin paketlari qamrovini tasdiqlang.
2. SEAGM tanlansa: rasmiy onboarding’dan API ruxsati oling; `SEAGM_UID`, `SEAGM_SECRET_KEY`, `SEAGM_API_ENV=sandbox` ni server secretlari orqali sozlang. Hozirgi SEAGM client faqat o‘qish operatsiyalarini qo‘llaydi.
3. Har bir paketga tasdiqlangan supplier type/region, haqiqiy wholesale/retail narx va mavjudlik kerak. **Admin → Top Up** orqali narx va mapping boshqariladi.
4. Shundan so‘ng supplier buyurtmasi adapterini rasmiy API bo‘yicha yozish va tasdiqlangan payment’dan keyin dispatch, idempotency, retry, muvaffaqiyatsiz yetkazish va refund’ni supplier sandbox’da tekshirish kerak.
5. Hozir avtomatik real yetkazish yopiq qoladi. Narx yoki API kaliti qo‘shilishi uni ishga tushirmaydi; Stripe test Top Up hech qanday UC jo‘natmaydi.

## Operator, yordam va himoya

**Admin → Team & business profile** orqali haqiqiy operator nomi/manzil/email, support mas’uli, ishlaydigan kun-soatlar, timezone, erishiladigan javob muddati, himoya qamrovi va istisnolarni to‘ldiring. Barcha ma’lumotlarni tekshirgandan keyin publish qiling. Yuridik/tax/publisher shartlarini tegishli mutaxassis bilan tekshiring. Tasdiqlanmagan 24/7 yoki moliyaviy kafolat yozmang.

## Kuzatuv va chiqarish mezonlari

- Desktop va telefon: home → qidiruv/filtr → mahsulot → savat → test checkout → order/refund yo‘lini tekshiring. Bo‘sh katalog, tarmoq uzilishi, disabled paketlar va qayta urinishlarni ham tekshiring.
- Keyboard: region dialog, custom select, menyu va formalarni sichqonchasiz tekshiring; mobile overflow va qo‘sh border bo‘lmasin.
- Vercel Analytics/Speed Insights va mavjud `?qa_metrics=1` diagnostikasini ishlating. Mahalliy natijani haqiqiy telefon yoki production capacity dalili deb olmang.
- Real savdo oldidan backup/restore mashqi, monitoring xabari, nizo/support va provider failure mashqlarini yakunlang. Mavjud `SUPPORT_AND_DISPUTES_RUNBOOK.md` va `GAME_AND_MARKET_DECISIONS.md` bilan birga foydalaning.

Asosiy shopping tarjimalari kengaytirilgan. Erkin sotuvchi matni tarjima qilinmaydi; to‘liq yuridik va ayrim admin/chat matnlari professional til tekshiruvi tugamaguncha English’da qolishi mumkin.

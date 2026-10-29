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

Ulangan connector: **NexusVault sandbox**, test rejimi. Connector sayt serveriga API kalitlarini o‘zi bermaydi. Connect ro‘yxatini o‘qish muvaffaqiyatli bo‘ldi; ro‘yxat bo‘sh. Pul yechilmaydigan ikki API Checkout sessiyasi tekshirildi: 96000 UZS → 9600000 Stripe birligi; 300 MYR → 30000 Stripe birligi. Ikkalasi test va unpaid holatida. Bu saytdagi webhook yoki fulfillment E2E tekshiruvi emas. Connector expire operatsiyasini bermadi; audit sessiyalari odatiy muddati tugashigacha sandbox’da qoladi.

Serverga sandbox cheklangan kaliti va shu sandbox hisob ID sini deployment secret sifatida kiriting. Kalitlarni chatga yoki Git’ga qo‘ymang:

- `PAYMENT_PROVIDER=stripe_test`
- `STRIPE_TEST_SECRET_KEY` — `rk_test_…` yoki test secret.
- `STRIPE_TEST_ACCOUNT_ID` — aynan tanlangan sandbox hisobi.
- `STRIPE_TEST_WEBHOOK_SECRET` — webhook endpoint signing secret.
- `PUBLIC_BASE_URL` — saytning HTTPS origin’i, path/query’siz.
- Production muhitidagi himoyalangan ichki sinov uchun mavjud `MARKETPLACE_INTERNAL_TESTING_ENABLED=true` alohida talab etiladi. Bu audit uni o‘zgartirmadi.

Sandbox Dashboard’da webhook endpoint sifatida `https://<your-origin>/api/webhooks/stripe-test` ni yarating va `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `checkout.session.async_payment_failed`, `charge.refunded`, `charge.dispute.created` hodisalarini ulang. Endpoint’ning signing secret qiymatini `STRIPE_TEST_WEBHOOK_SECRET` sifatida saqlang. Production `/api/health` hozir `stripe_test`, `internal_testing`, `sales_enabled=false` ko‘rsatdi. Bu sozlamalar borligini bildiradi, payment/webhook E2E tasdig‘i emas. Mahalliy QA’da test secretlari yo‘q; avtomatik testlar imzolangan webhook va SDK javoblarini izolyatsiyada tekshiradi.

Ichki UZS → Stripe minor-unit konvertatsiyasi checkout, webhook, refund va settlement chegaralarida bajariladi. Eski versiyada noto‘g‘ri kichik summa bilan yaratilgan sessiyalar avtomatik yangi charge yaratmaydi: operator ularni sandbox’da tekshirib, reconcile qilishi kerak.

Live launch uchun UK operatori, mahsulot/market qamrovi, Stripe roziligi, real live adapter va webhook/refund/Connect tekshiruvlari alohida kerak. Sandbox muvaffaqiyati live ruxsat bermaydi. Display currency tanlovi charge yoki settlement valyutasini o‘zi o‘zgartirmaydi.

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

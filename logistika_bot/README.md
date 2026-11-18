# World Forum Consulting — zayavka boti

Odam postdagi **"Ro'yxatdan o'tish"** linkini bosadi → bot ism, familiya, telefon, viloyat va ingliz tili darajasini so'raydi →
zayavka **Telegram guruhingizga** (va xohlasangiz **Google Sheets** ga) darhol tushadi.

## 1. Sozlash (bir marta)
1. **@BotFather** → `/newbot` → yangi bot yarating, tokenni oling.
2. Zayavkalar uchun Telegram guruh oching, botni guruhga qo'shing va guruhda `/id` deb yozing — `Chat ID` ni oling.
   O'zingizning ID ingiz ham shu yerda chiqadi.
3. `.env.example` faylini `.env` deb nusxalang va to'ldiring:
   - `BOT_TOKEN` — 1-qadamdagi token
   - `LEADS_CHAT_IDS` — guruh ID si (masalan `-1001234567890`)
   - `ADMIN_IDS` — sizning ID ingiz
4. (Ixtiyoriy) Google Sheets: `google_sheets.gs` faylidagi ko'rsatmaga amal qiling va URL ni `SHEETS_WEBHOOK_URL` ga qo'ying.

## 2. Ishga tushirish
```
pip install -r requirements.txt
python bot.py
```

## 3. Postga link
Postdagi "Ro'yxatdan o'tish" so'ziga shu linkni ulang:
```
https://t.me/BOT_USERNAME?start=post1
```
`post1` o'rniga istalgan nom qo'ying (masalan `video_noyabr`) — zayavkada **Manba** bo'lib ko'rinadi,
qaysi post ko'proq odam olib kelganini bilasiz.

## Kanalga tugmali post joylash (/post)
1. Botni kanalingizga **admin** qilib qo'shing ("Xabar joylash" huquqi bilan).
2. `.env` ga `CHANNEL_ID=@kanalingiz` yozing va botni qayta yoqing.
3. Botga `/post` yozing → videoni matni bilan yuboring → manba nomini yozing (`video1`)
   → «✅ Kanalga yuborish» ni bosing. Post kanalda «📝 Ro'yxatdan o'tish» tugmasi bilan chiqadi.

## Admin buyruqlari
- `/post` — kanalga tugmali post joylash
- `/stats` — jami va bugungi zayavkalar soni
- `/export` — barcha zayavkalar CSV (Excel) faylda — CRM ga import qilish uchun
- `/id` — chat ID ni ko'rsatadi

## CRM (Fieldy) ga ulash
`.env` da `CRM_WEBHOOK_URL` (kontakt yaratish manzili) va `CRM_API_KEY` ni to'ldiring.
Kalit `Authorization: Bearer` emas, boshqa sarlavhada yuborilsa — `CRM_AUTH_HEADER` ga o'sha nomni yozing
(masalan `X-API-Key`).

Bot Fieldy ga shunday JSON yuboradi:
```json
{
  "firstName": "Aziz", "lastName": "Karimov", "phone": "+998901234567",
  "source": "TELEGRAM", "sourceDetail": "video1", "region": "Samarqand",
  "telegram": "@aziz", "notes": "Ingliz tili: Yaxshi (B2)\nTelegram ID: ...\nZayavka #2 (...)"
}
```
Toshkent shahri tanlansa `city: "Toshkent"` ham qo'shiladi. Bo'sh maydonlar yuborilmaydi.
Fieldy xato qaytarsa, guruhdagi zayavka xabari ostida ⚠️ bilan ko'rinadi.

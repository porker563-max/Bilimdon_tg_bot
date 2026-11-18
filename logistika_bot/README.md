# Amanah Logistics Academy — zayavka boti

Odam postdagi **"Ro'yxatdan o'tish"** linkini bosadi → bot ism, telefon va ingliz tili darajasini so'raydi →
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

## Admin buyruqlari
- `/stats` — jami va bugungi zayavkalar soni
- `/export` — barcha zayavkalar CSV (Excel) faylda — CRM ga import qilish uchun
- `/id` — chat ID ni ko'rsatadi

## CRM (Fieldy) ga ulash
Fieldy da API/webhook manzili bo'lsa, `CRM_WEBHOOK_URL` va `CRM_API_KEY` ni to'ldirish kifoya —
bot har bir zayavkani JSON qilib yuboradi. Fieldy kutadigan aniq format ma'lum bo'lgach moslashtiriladi.

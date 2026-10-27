# Kurslar Telegram boti

## Ishga tushirish
1. `pip install -r requirements.txt`
2. `.env.example` ni `.env` ga nusxalang va to'ldiring:
   - `BOT_TOKEN` — @BotFather dan
   - `OWNER_ID` — egasining Telegram ID si (@userinfobot orqali)
   - `CARD_NUMBER`, `CARD_OWNER` — to'lov qabul qilinadigan karta
3. `python bot.py`

## Kanallarni ulash
- Har bir kurs uchun alohida yopiq kanal yarating.
- Botni kanalga **admin** qiling ("Taklif havolalarini yaratish" huquqi bilan).
- Kanal ID sini oling (masalan, kanaldan xabarni @userinfobot ga forward qiling): `-100...`
- Bot ichida: **👑 Owner panel → 📚 Kurs qo'shish** orqali nom, narx va kanal ID ni kiriting.
- Dastlabki 3 ta namuna kursda kanal yo'q — ularni o'chirib, o'z kurslaringizni qo'shing.

## Rollar
- **Foydalanuvchi:** kurs tanlaydi → to'lov cheki / nogironlik hujjati / kundalik bahosi yuboradi.
- **Admin:** arizalarni ko'radi, «✅ Tasdiqlash» yoki «❌ Bekor qilish» bosadi.
  Tasdiqlansa, foydalanuvchiga yopiq kanal linki avtomatik yuboriladi.
- **Owner:** adminlarni ID bo'yicha qo'shadi/o'chiradi, kurslarni boshqaradi, bot nomi/tavsifi/rasmini yangilaydi.

Ma'lumotlar `bot.db` (SQLite) faylida saqlanadi.

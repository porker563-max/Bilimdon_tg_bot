# World Forum Consulting — zayavka boti

Kanaldagi postning tagidagi **"📝 Ro'yxatdan o'tish"** tugmasi bosilganda bot ochiladi. Bot quyidagilarni so'raydi:
ism → familiya → telefon → viloyat → ingliz tili → qo'shimcha ma'lumot (ixtiyoriy).
Zayavka **Telegram guruhga**, **Fieldy CRM**ga va (xohlasangiz) **Google Sheets**ga tushadi.

---

## 1. Telegram tomonda tayyorgarlik
1. **@BotFather** → `/newbot` → bot yarating va **token**ni oling.
2. **Guruh** oching (zayavkalar shu yerga keladi) va botni unga qo'shing.
3. Botni **kanalingizga admin** qiling ("Xabar joylash" huquqi bilan). Bu `/post` uchun kerak.

## 2. PythonAnywhere ga o'rnatish (bir marta)
Pullik tarif kerak, chunki bot 24/7 ishlashi uchun **Always-on task** ishlatiladi.

1. pythonanywhere.com saytida **Consoles → Bash** ni oching.
2. Kodni yuklab oling:
   ```
   git clone -b ccr-7a872b4e-7vn55i https://github.com/porker563-max/Bilimdon_tg_bot.git
   ```
   Repo yopiq bo'lsa, GitHub username va parol so'raladi. Parol o'rniga GitHub **Personal access token** kiritiladi.
3. Kutubxonalarni o'rnating:
   ```
   cd ~/Bilimdon_tg_bot/world_forum_bot
   pip3.11 install --user -r requirements.txt
   ```
4. Sozlamalar faylini yarating:
   ```
   cp .env.example .env
   nano .env
   ```
   Hozircha faqat `BOT_TOKEN` ni to'ldirsangiz kifoya. Saqlash: **Ctrl+O** → **Enter**, chiqish: **Ctrl+X**.
   (Yoki PythonAnywhere'ning **Files** bo'limida `.env` faylini oching va brauzerda tahrirlang.)
5. Sinab ko'ring:
   ```
   python3.11 bot.py
   ```
   `Bot ishga tushdi: @...` chiqsa, ishlayapti. Endi guruhda `/id@BotUsername` deb yozing va **Chat ID** hamda
   **Sizning ID** ni oling. **Ctrl+C** bilan to'xtating, `.env` da `LEADS_CHAT_IDS`, `ADMIN_IDS` va `CHANNEL_ID`
   ni to'ldiring.
6. **24/7 ishga tushirish:** **Tasks** sahifasi → **Always-on tasks** bo'limiga quyidagi buyruqni yozing
   (`USERNAME` o'rniga PythonAnywhere'dagi login nomingizni qo'ying) va **Create** ni bosing:
   ```
   python3.11 /home/USERNAME/Bilimdon_tg_bot/world_forum_bot/bot.py
   ```
   Bot to'xtab qolsa ham, PythonAnywhere uni o'zi qayta ishga tushiradi.
   ⚠️ Botni Bash konsolda ham, Always-on task'da ham **bir vaqtda** yoqmang. Ikki nusxa bir-biriga xalaqit beradi.

**Xatolarni ko'rish:** Tasks sahifasida task yonidagi **log** tugmasi.

## 3. Kodni yangilash
Bash konsolda:
```
cd ~/Bilimdon_tg_bot && git pull
```
Keyin **Tasks** sahifasida task'ni **Restart** qiling. `.env` va baza (`leads.db`) o'zgarmaydi.

---

## Kanalga tugmali post (/post)
Botga `/post` → videoni matni bilan yuborasiz → manba nomini yozasiz (`video1`) → **✅ Kanalga yuborish**.
Post kanalda **📝 Ro'yxatdan o'tish** tugmasi bilan chiqadi. Zayavkada "Manba: video1" deb ko'rinadi.

Boshqa birovning kanalida reklama qilsangiz, ularga shu linkni bering:
`https://t.me/BOT_USERNAME?start=reklama1` (nomda faqat lotin harf, raqam, `_` va `-` bo'lsin).

## Admin buyruqlari
- `/post` — kanalga tugmali post
- `/stats` — jami va bugungi zayavkalar soni
- `/export` — barcha zayavkalar Excel (CSV) faylda
- `/id` — chat ID (hamma ishlata oladi)

## Fieldy CRM
`.env` da `CRM_WEBHOOK_URL` (kontakt yaratish manzili) va `CRM_API_KEY` ni to'ldiring. Bot quyidagini yuboradi:
```json
{
  "firstName": "Aziz", "lastName": "Karimov", "phone": "+998901234567",
  "source": "TELEGRAM", "sourceDetail": "video1", "region": "Namangan", "telegram": "@aziz",
  "notes": "Ingliz tili: IELTS sertifikatim bor\nQo'shimcha ma'lumot: ...\nTelegram ID: ...\nZayavka #1 (...)"
}
```
Fieldy xato qaytarsa, guruhdagi zayavka ostida ⚠️ bilan ko'rinadi.

## Google Sheets (ixtiyoriy)
`google_sheets.gs` faylidagi ko'rsatmaga amal qiling va olingan URL ni `SHEETS_WEBHOOK_URL` ga qo'ying.

"""Amanah Logistics Academy — zayavka (ro'yxatdan o'tish) boti.

Oqim: /start -> ism -> telefon -> ingliz tili darajasi -> zayavka saqlanadi va
  1) adminlar guruhiga / chatiga yuboriladi,
  2) (ixtiyoriy) Google Sheets jadvaliga yoziladi,
  3) (ixtiyoriy) CRM webhook manziliga JSON qilib yuboriladi (Fieldy va h.k.).

Telefonda (Termux) oson o'rnatilishi uchun og'ir kutubxonalarsiz yozilgan:
faqat aiohttp, aiosqlite va python-dotenv kerak.
"""
import asyncio
import csv
import html
import io
import json
import logging
import os
import re
from datetime import datetime

import aiohttp
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Zayavkalar yuboriladigan chat(lar): guruh ID (-100...) yoki shaxsiy ID. Vergul bilan bir nechta.
LEADS_CHAT_IDS = [int(x) for x in os.getenv("LEADS_CHAT_IDS", "").replace(" ", "").split(",") if x]
# /export va /stats buyruqlarini ishlata oladigan odamlar ID lari.
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "").strip()
CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "").strip()
CRM_API_KEY = os.getenv("CRM_API_KEY", "").strip()
# Kalit qaysi sarlavhada yuboriladi. "Authorization" bo'lsa — "Bearer <kalit>", boshqa bo'lsa — kalitning o'zi.
CRM_AUTH_HEADER = os.getenv("CRM_AUTH_HEADER", "Authorization").strip() or "Authorization"
DB_PATH = os.getenv("DB_PATH", "leads.db")
API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")

LEVELS = {
    "0": "Boshlang'ich (A1–A2)",
    "1": "O'rta (B1)",
    "2": "Yaxshi (B2)",
    "3": "Juda yaxshi (C1–C2)",
}
REGIONS = [
    "Toshkent shahri", "Toshkent viloyati", "Andijon", "Buxoro", "Farg'ona", "Jizzax",
    "Xorazm", "Namangan", "Navoiy", "Qashqadaryo", "Qoraqalpog'iston", "Samarqand",
    "Sirdaryo", "Surxondaryo", "Boshqa davlat",
]

log = logging.getLogger("logistika_bot")

# Foydalanuvchi qaysi savolda turgani:
# {user_id: {"step": "first_name"|"last_name"|"phone"|"region"|"level", ...}}
STATE: dict[int, dict] = {}


# ───────────────────────── Telegram API ─────────────────────────
class TG:
    def __init__(self, session: aiohttp.ClientSession, token: str):
        self.s = session
        self.url = f"{API_BASE}/bot{token}/"

    async def call(self, method: str, http_timeout: float = 30, **params):
        payload = {k: v for k, v in params.items() if v is not None}
        async with self.s.post(self.url + method, json=payload,
                               timeout=aiohttp.ClientTimeout(total=http_timeout)) as r:
            data = await r.json(content_type=None)
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    async def send(self, chat_id, text, reply_markup=None):
        return await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                               disable_web_page_preview=True, reply_markup=reply_markup)

    async def send_document(self, chat_id, filename: str, content: bytes, caption: str = ""):
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("caption", caption)
        form.add_field("document", content, filename=filename, content_type="text/csv")
        async with self.s.post(self.url + "sendDocument", data=form,
                               timeout=aiohttp.ClientTimeout(total=60)) as r:
            data = await r.json(content_type=None)
        if not data.get("ok"):
            raise RuntimeError(f"sendDocument: {data.get('description')}")


REMOVE_KB = {"remove_keyboard": True}
PHONE_KB = {
    "keyboard": [[{"text": "📱 Raqamni yuborish", "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
LEVEL_KB = {"inline_keyboard": [[{"text": v, "callback_data": f"lvl:{k}"}] for k, v in LEVELS.items()]}
REGION_KB = {"inline_keyboard": [
    [{"text": r, "callback_data": f"reg:{i + j}"} for j, r in enumerate(REGIONS[i:i + 2])]
    for i in range(0, len(REGIONS), 2)
]}


# ───────────────────────── Database ─────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS leads(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Eski bazaga yangi ustunlarni qo'shish.
        cur = await db.execute("PRAGMA table_info(leads)")
        cols = {row[1] for row in await cur.fetchall()}
        for col in ("first_name", "last_name", "region"):
            if col not in cols:
                await db.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT DEFAULT ''")
        await db.commit()


async def save_lead(lead: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO leads(tg_id, username, full_name, first_name, last_name, phone, region,"
            " level, source, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (lead["tg_id"], lead["username"], lead["full_name"], lead["first_name"], lead["last_name"],
             lead["phone"], lead["region"], lead["level"], lead["source"], lead["created_at"]),
        )
        await db.commit()
        return cur.lastrowid


async def all_leads():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM leads ORDER BY id")
        return await cur.fetchall()


# ───────────────────────── Tashqi yuborish ─────────────────────────
async def post_json(session: aiohttp.ClientSession, url: str, payload: dict, headers: dict) -> None:
    async with session.post(url, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=20)) as r:
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")


def fieldy_payload(lead: dict) -> dict:
    """Fieldy CRM kutadigan formatdagi kontakt."""
    notes = (f"Ingliz tili: {lead['level']}\n"
             f"Telegram ID: {lead['tg_id']}\n"
             f"Zayavka #{lead['id']} ({lead['created_at']})")
    p = {
        "firstName": lead["first_name"],
        "lastName": lead["last_name"],
        "phone": lead["phone"],
        "source": "TELEGRAM",
        "sourceDetail": lead["source"] or "Telegram bot",
        "region": lead["region"],
        "telegram": f"@{lead['username']}" if lead["username"] else "",
        "notes": notes,
    }
    if lead["region"] == "Toshkent shahri":
        p["city"] = "Toshkent"
    return {k: v for k, v in p.items() if v}


def crm_headers() -> dict:
    if not CRM_API_KEY:
        return {}
    if CRM_AUTH_HEADER.lower() == "authorization":
        return {"Authorization": f"Bearer {CRM_API_KEY}"}
    return {CRM_AUTH_HEADER: CRM_API_KEY}


async def deliver(tg: TG, lead: dict) -> None:
    """Zayavkani Google Sheets / CRM ga va adminlar chatiga yuboradi."""
    uname = f"@{lead['username']}" if lead["username"] else "—"
    text = (
        f"🆕 <b>Yangi zayavka #{lead['id']}</b>\n\n"
        f"👤 Ism: <b>{html.escape(lead['full_name'])}</b>\n"
        f"📞 Telefon: <code>{html.escape(lead['phone'])}</code>\n"
        f"🗺 Viloyat: {html.escape(lead['region'])}\n"
        f"🇬🇧 Ingliz tili: {html.escape(lead['level'])}\n"
        f"💬 Telegram: {html.escape(uname)} (<a href=\"tg://user?id={lead['tg_id']}\">profil</a>)\n"
        f"📍 Manba: {html.escape(lead['source'] or '—')}\n"
        f"🕒 {lead['created_at']}"
    )
    errors = []
    targets = []
    if SHEETS_WEBHOOK_URL:
        targets.append(("Google Sheets", SHEETS_WEBHOOK_URL, lead, {}))
    if CRM_WEBHOOK_URL:
        targets.append(("CRM", CRM_WEBHOOK_URL, fieldy_payload(lead), crm_headers()))
    for name, url, payload, headers in targets:
        try:
            await post_json(tg.s, url, payload, headers)
        except Exception as e:  # noqa: BLE001
            log.exception("%s ga yuborib bo'lmadi", name)
            errors.append(f"{name}: {e}")
    if errors:
        text += "\n\n⚠️ " + html.escape("; ".join(errors))
    for chat_id in LEADS_CHAT_IDS:
        try:
            await tg.send(chat_id, text)
        except Exception:  # noqa: BLE001
            log.exception("Chat %s ga yuborib bo'lmadi", chat_id)


# ───────────────────────── Xabarlarni qayta ishlash ─────────────────────────
async def on_message(tg: TG, m: dict):
    chat_id = m["chat"]["id"]
    user = m.get("from") or {}
    uid = user.get("id")
    text = (m.get("text") or "").strip()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@", 1)[0].lower() if cmd.startswith("/") else ""

    if cmd == "/id":
        await tg.send(chat_id, f"Chat ID: <code>{chat_id}</code>\nSizning ID: <code>{uid}</code>")
        return
    if cmd == "/stats" and uid in ADMIN_IDS:
        rows = await all_leads()
        today = datetime.now().strftime("%Y-%m-%d")
        n_today = sum(1 for r in rows if r["created_at"].startswith(today))
        await tg.send(chat_id, f"📊 Jami zayavkalar: <b>{len(rows)}</b>\nBugun: <b>{n_today}</b>")
        return
    if cmd == "/export" and uid in ADMIN_IDS:
        await export(tg, chat_id)
        return

    # Ro'yxatdan o'tish faqat shaxsiy chatda.
    if m["chat"].get("type") != "private":
        return

    if cmd == "/start":
        STATE[uid] = {"step": "first_name", "source": re.sub(r"[^\w-]", "", arg)[:64]}
        await tg.send(
            chat_id,
            "Assalomu alaykum! 👋\n\n"
            "<b>Amanah Logistics Academy</b>ning onlayn logistika kursiga ro'yxatdan o'tish uchun "
            "bir nechta qisqa savolga javob bering. Mutaxassislarimiz siz bilan tez orada bog'lanishadi.\n\n"
            "1️⃣ Ismingizni yozing:",
            REMOVE_KB,
        )
        return

    st = STATE.get(uid)
    if not st:
        await tg.send(chat_id, "Ro'yxatdan o'tish uchun /start ni bosing.")
        return

    if st["step"] in ("first_name", "last_name"):
        word = " ".join(text.split())
        if not (2 <= len(word) <= 40) or word.startswith("/") or any(c.isdigit() for c in word):
            what = "ismingizni (masalan: Aziz)" if st["step"] == "first_name" else "familiyangizni (masalan: Karimov)"
            await tg.send(chat_id, f"Iltimos, {what} to'g'ri yozing.")
            return
        if st["step"] == "first_name" and " " in word:  # "Aziz Karimov" deb birdaniga yozsa
            first, last = word.split(" ", 1)
            st.update(first_name=first, last_name=last, step="phone")
            await tg.send(
                chat_id,
                "3️⃣ Telefon raqamingizni yuboring — pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing "
                "yoki qo'lda yozing (masalan: +998901234567).",
                PHONE_KB,
            )
            return
        if st["step"] == "first_name":
            st.update(first_name=word, step="last_name")
            await tg.send(chat_id, "2️⃣ Familiyangizni yozing:")
            return
        st.update(last_name=word, step="phone")
        await tg.send(
            chat_id,
            "3️⃣ Telefon raqamingizni yuboring — pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing "
            "yoki qo'lda yozing (masalan: +998901234567).",
            PHONE_KB,
        )
    elif st["step"] == "phone":
        raw = (m.get("contact") or {}).get("phone_number") or text
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 9:  # 901234567 -> 998901234567
            digits = "998" + digits
        if not (10 <= len(digits) <= 15):
            await tg.send(chat_id, "Raqam noto'g'ri ko'rinadi. Iltimos, qaytadan yuboring (masalan: +998901234567).")
            return
        st.update(phone="+" + digits, step="region")
        await tg.send(chat_id, "✅ Raqam qabul qilindi.", REMOVE_KB)
        await tg.send(chat_id, "4️⃣ Qaysi viloyatda yashaysiz?", REGION_KB)
    elif st["step"] == "region":
        await tg.send(chat_id, "Iltimos, yuqoridagi tugmalardan birini tanlang 👆", REGION_KB)
    elif st["step"] == "level":
        await tg.send(chat_id, "Iltimos, yuqoridagi tugmalardan birini tanlang 👆", LEVEL_KB)


async def mark_chosen(tg: TG, msg: dict, text: str):
    """Tugmali xabarni tanlangan javob bilan almashtiradi (tugmalar yo'qoladi)."""
    if not msg:
        return
    try:
        await tg.call("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                      text=text, parse_mode="HTML")
    except Exception:  # noqa: BLE001
        pass


async def on_callback(tg: TG, cb: dict):
    user = cb["from"]
    uid = user["id"]
    msg = cb.get("message") or {}
    data = cb.get("data") or ""
    st = STATE.get(uid)
    kind, _, val = data.partition(":")
    await tg.call("answerCallbackQuery", callback_query_id=cb["id"])
    chat_id = msg.get("chat", {}).get("id", uid)

    if st and st.get("step") == "region" and kind == "reg" and val.isdigit() and int(val) < len(REGIONS):
        region = REGIONS[int(val)]
        st.update(region=region, step="level")
        await mark_chosen(tg, msg, f"4️⃣ Viloyat: <b>{html.escape(region)}</b>")
        await tg.send(chat_id, "5️⃣ Ingliz tilini qay darajada bilasiz?", LEVEL_KB)
        return

    level = LEVELS.get(val) if kind == "lvl" else None
    if not st or st.get("step") != "level" or not level:
        return
    STATE.pop(uid, None)
    lead = {
        "tg_id": uid,
        "username": user.get("username") or "",
        "first_name": st["first_name"],
        "last_name": st["last_name"],
        "full_name": f"{st['first_name']} {st['last_name']}",
        "phone": st["phone"],
        "region": st["region"],
        "level": level,
        "source": st.get("source", ""),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    lead["id"] = await save_lead(lead)
    await mark_chosen(tg, msg, f"5️⃣ Ingliz tili darajasi: <b>{html.escape(level)}</b>")
    await tg.send(
        chat_id,
        "🎉 <b>Rahmat! Zayavkangiz qabul qilindi.</b>\n\n"
        "Mutaxassislarimiz tez orada siz bilan bog'lanib, kurs haqida batafsil ma'lumot berishadi. 📞",
    )
    asyncio.create_task(deliver(tg, lead))


async def export(tg: TG, chat_id: int):
    rows = await all_leads()
    if not rows:
        await tg.send(chat_id, "Hali zayavka yo'q.")
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Ism", "Familiya", "Telefon", "Viloyat", "Ingliz tili", "Telegram", "Telegram ID",
                "Manba", "Sana"])
    for r in rows:
        first, last = r["first_name"], r["last_name"]
        if not first:  # eski zayavkalar (ism-familiya birga yozilgan)
            first, _, last = r["full_name"].partition(" ")
        w.writerow([r["id"], first, last, r["phone"], r["region"], r["level"],
                    f"@{r['username']}" if r["username"] else "", r["tg_id"], r["source"], r["created_at"]])
    data = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM — Excel o'zbek harflarini to'g'ri ochishi uchun
    await tg.send_document(chat_id, f"zayavkalar_{datetime.now():%Y%m%d}.csv", data,
                           f"📥 {len(rows)} ta zayavka. Bu faylni CRM ga import qilishingiz mumkin.")


async def handle(tg: TG, update: dict):
    try:
        if "message" in update:
            await on_message(tg, update["message"])
        elif "callback_query" in update:
            await on_callback(tg, update["callback_query"])
    except Exception:  # noqa: BLE001
        log.exception("Update ni qayta ishlashda xato: %s", json.dumps(update)[:300])


# ───────────────────────── Ishga tushirish ─────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylini to'ldiring (.env.example ga qarang).")
    if not LEADS_CHAT_IDS:
        log.warning("LEADS_CHAT_IDS bo'sh — zayavkalar faqat bazaga yoziladi. Guruhda /id yozib ID ni oling.")
    await init_db()
    async with aiohttp.ClientSession() as session:
        tg = TG(session, BOT_TOKEN)
        me = await tg.call("getMe")
        await tg.call("deleteWebhook")
        log.info("Bot ishga tushdi: @%s — to'xtatish uchun Ctrl+C", me["username"])
        offset = 0
        while True:
            try:
                updates = await tg.call("getUpdates", http_timeout=70, offset=offset, limit=50,
                                        timeout=50, allowed_updates=["message", "callback_query"])
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — internet uzilsa, kutib qayta urinadi
                log.warning("Telegram bilan aloqa yo'q (%s). 5 soniyadan keyin qayta urinaman...", e)
                await asyncio.sleep(5)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                await handle(tg, u)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")

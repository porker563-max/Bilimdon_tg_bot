"""Amanah Logistics Academy — zayavka (ro'yxatdan o'tish) boti.

Oqim: /start -> ism -> telefon -> ingliz tili darajasi -> zayavka saqlanadi va
  1) adminlar guruhiga / chatiga yuboriladi,
  2) (ixtiyoriy) Google Sheets jadvaliga yoziladi,
  3) (ixtiyoriy) CRM webhook manziliga JSON qilib yuboriladi (Fieldy va h.k.).
"""
import asyncio
import csv
import html
import io
import logging
import os
import re
from datetime import datetime, timezone

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Zayavkalar yuboriladigan chat(lar): guruh ID (-100...) yoki shaxsiy ID. Vergul bilan bir nechta.
LEADS_CHAT_IDS = [int(x) for x in os.getenv("LEADS_CHAT_IDS", "").replace(" ", "").split(",") if x]
# /export va /stats buyruqlarini ishlata oladigan odamlar ID lari.
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "").strip()
CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "").strip()
CRM_API_KEY = os.getenv("CRM_API_KEY", "").strip()
DB_PATH = os.getenv("DB_PATH", "leads.db")

LEVELS = {
    "0": "Boshlang'ich (A1–A2)",
    "1": "O'rta (B1)",
    "2": "Yaxshi (B2)",
    "3": "Juda yaxshi (C1–C2)",
}

router = Router()
log = logging.getLogger("logistika_bot")


class Form(StatesGroup):
    name = State()
    phone = State()
    level = State()


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
        await db.commit()


async def save_lead(lead: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO leads(tg_id, username, full_name, phone, level, source, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (lead["tg_id"], lead["username"], lead["full_name"], lead["phone"],
             lead["level"], lead["source"], lead["created_at"]),
        )
        await db.commit()
        return cur.lastrowid


async def all_leads():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM leads ORDER BY id")
        return await cur.fetchall()


# ───────────────────────── Tashqi yuborish ─────────────────────────
async def post_json(url: str, payload: dict, headers: dict | None = None) -> None:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload, headers=headers or {}) as r:
            if r.status >= 400:
                raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")


async def deliver(bot: Bot, lead: dict) -> None:
    """Zayavkani adminlarga, Google Sheets ga va CRM ga yuboradi. Xato bo'lsa — log + adminlarga ogohlantirish."""
    uname = f"@{lead['username']}" if lead["username"] else "—"
    text = (
        f"🆕 <b>Yangi zayavka #{lead['id']}</b>\n\n"
        f"👤 Ism: <b>{html.escape(lead['full_name'])}</b>\n"
        f"📞 Telefon: <code>{html.escape(lead['phone'])}</code>\n"
        f"🇬🇧 Ingliz tili: {html.escape(lead['level'])}\n"
        f"💬 Telegram: {html.escape(uname)} (<a href=\"tg://user?id={lead['tg_id']}\">profil</a>)\n"
        f"📍 Manba: {html.escape(lead['source'] or '—')}\n"
        f"🕒 {lead['created_at']}"
    )
    errors = []

    targets = []
    if SHEETS_WEBHOOK_URL:
        targets.append(("Google Sheets", SHEETS_WEBHOOK_URL, {}))
    if CRM_WEBHOOK_URL:
        h = {"Authorization": f"Bearer {CRM_API_KEY}"} if CRM_API_KEY else {}
        targets.append(("CRM", CRM_WEBHOOK_URL, h))
    for name, url, headers in targets:
        try:
            await post_json(url, lead, headers)
        except Exception as e:  # noqa: BLE001
            log.exception("%s ga yuborib bo'lmadi", name)
            errors.append(f"{name}: {e}")

    if errors:
        text += "\n\n⚠️ " + html.escape("; ".join(errors))
    for chat_id in LEADS_CHAT_IDS:
        try:
            await bot.send_message(chat_id, text)
        except Exception:  # noqa: BLE001
            log.exception("Chat %s ga yuborib bo'lmadi", chat_id)


# ───────────────────────── Klaviaturalar ─────────────────────────
def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def level_kb():
    b = InlineKeyboardBuilder()
    for key, label in LEVELS.items():
        b.button(text=label, callback_data=f"lvl:{key}")
    b.adjust(1)
    return b.as_markup()


# ───────────────────────── Foydalanuvchi oqimi ─────────────────────────
@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    await state.update_data(source=(command.args or "")[:64])
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "<b>Amanah Logistics Academy</b>ning onlayn logistika kursiga ro'yxatdan o'tish uchun "
        "3 ta qisqa savolga javob bering. Mutaxassislarimiz siz bilan tez orada bog'lanishadi.\n\n"
        "1️⃣ Ism va familiyangizni yozing:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Form.name)


@router.message(Form.name, F.text)
async def got_name(message: Message, state: FSMContext):
    name = " ".join(message.text.split())
    if not (2 <= len(name) <= 60) or name.startswith("/"):
        await message.answer("Iltimos, ism va familiyangizni to'g'ri yozing (masalan: Aziz Karimov).")
        return
    await state.update_data(full_name=name)
    await message.answer(
        "2️⃣ Telefon raqamingizni yuboring — pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing "
        "yoki qo'lda yozing (masalan: +998901234567).",
        reply_markup=phone_kb(),
    )
    await state.set_state(Form.phone)


@router.message(Form.phone, F.contact | F.text)
async def got_phone(message: Message, state: FSMContext):
    raw = message.contact.phone_number if message.contact else message.text
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:  # 901234567 -> 998901234567
        digits = "998" + digits
    if not (10 <= len(digits) <= 15):
        await message.answer("Raqam noto'g'ri ko'rinadi. Iltimos, qaytadan yuboring (masalan: +998901234567).")
        return
    await state.update_data(phone="+" + digits)
    await message.answer("✅ Raqam qabul qilindi.", reply_markup=ReplyKeyboardRemove())
    await message.answer("3️⃣ Ingliz tilini qay darajada bilasiz?", reply_markup=level_kb())
    await state.set_state(Form.level)


@router.message(Form.level)
async def level_hint(message: Message):
    await message.answer("Iltimos, yuqoridagi tugmalardan birini tanlang 👆", reply_markup=level_kb())


@router.callback_query(Form.level, F.data.startswith("lvl:"))
async def got_level(cb: CallbackQuery, state: FSMContext, bot: Bot):
    level = LEVELS.get(cb.data.split(":", 1)[1])
    if not level:
        await cb.answer()
        return
    data = await state.get_data()
    await state.clear()
    lead = {
        "tg_id": cb.from_user.id,
        "username": cb.from_user.username or "",
        "full_name": data["full_name"],
        "phone": data["phone"],
        "level": level,
        "source": data.get("source", ""),
        "created_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }
    lead["id"] = await save_lead(lead)
    await cb.message.edit_text(f"3️⃣ Ingliz tili darajasi: <b>{html.escape(level)}</b>")
    await cb.message.answer(
        "🎉 <b>Rahmat! Zayavkangiz qabul qilindi.</b>\n\n"
        "Mutaxassislarimiz tez orada siz bilan bog'lanib, kurs haqida batafsil ma'lumot berishadi. 📞"
    )
    await cb.answer()
    asyncio.create_task(deliver(bot, lead))


# ───────────────────────── Admin buyruqlari ─────────────────────────
@router.message(Command("id"))
async def show_id(message: Message):
    """Guruh yoki shaxsiy chat ID sini bilish uchun (sozlashda kerak bo'ladi)."""
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>\nSizning ID: <code>{message.from_user.id}</code>")


@router.message(Command("stats"), F.from_user.id.in_(ADMIN_IDS))
async def stats(message: Message):
    rows = await all_leads()
    today = datetime.now().strftime("%Y-%m-%d")
    n_today = sum(1 for r in rows if r["created_at"].startswith(today))
    await message.answer(f"📊 Jami zayavkalar: <b>{len(rows)}</b>\nBugun: <b>{n_today}</b>")


@router.message(Command("export"), F.from_user.id.in_(ADMIN_IDS))
async def export(message: Message):
    rows = await all_leads()
    if not rows:
        await message.answer("Hali zayavka yo'q.")
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Ism", "Telefon", "Ingliz tili", "Telegram", "Telegram ID", "Manba", "Sana"])
    for r in rows:
        w.writerow([r["id"], r["full_name"], r["phone"], r["level"],
                    f"@{r['username']}" if r["username"] else "", r["tg_id"], r["source"], r["created_at"]])
    data = ("﻿" + buf.getvalue()).encode("utf-8")  # BOM — Excel o'zbek harflarini to'g'ri ochishi uchun
    await message.answer_document(
        BufferedInputFile(data, filename=f"zayavkalar_{datetime.now():%Y%m%d}.csv"),
        caption=f"📥 {len(rows)} ta zayavka. Bu faylni CRM ga import qilishingiz mumkin.",
    )


# ───────────────────────── Ishga tushirish ─────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylini to'ldiring (.env.example ga qarang).")
    if not LEADS_CHAT_IDS:
        log.warning("LEADS_CHAT_IDS bo'sh — zayavkalar faqat bazaga yoziladi, hech kimga yuborilmaydi.")
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

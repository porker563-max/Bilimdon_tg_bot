import asyncio
import html
import io
import logging
import os
import time

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 0000 0000 0000")
CARD_OWNER = os.getenv("CARD_OWNER", "ISM FAMILIYA")
INVITE_MODE = os.getenv("INVITE_MODE", "single")  # single = bir martalik, permanent = doimiy
DB_PATH = os.getenv("DB_PATH", "bot.db")

KIND_LABEL = {
    "buy": "💳 Sotib olish (to'lov)",
    "dis": "♿ Imkoniyati cheklangan (bepul)",
    "act": "🌟 Faol yoshlar (bepul)",
}
STATUS_LABEL = {
    "pending": "⏳ Ko'rib chiqilmoqda",
    "approved": "✅ Tasdiqlangan",
    "rejected": "❌ Rad etilgan",
}

router = Router()


# ───────────────────────── Database ─────────────────────────
async def q(sql, params=(), one=False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchone() if one else await cur.fetchall()


async def ex(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, params)
        await db.commit()
        return cur.lastrowid


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                tg_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS admins(
                tg_id INTEGER PRIMARY KEY,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS courses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                channel_id INTEGER,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                file_id TEXT,
                file_type TEXT,
                status TEXT DEFAULT 'pending',
                admin_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await db.commit()


async def is_admin(uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    return bool(await q("SELECT 1 FROM admins WHERE tg_id=?", (uid,), one=True))


async def all_admin_ids() -> list[int]:
    ids = {r["tg_id"] for r in await q("SELECT tg_id FROM admins")}
    if OWNER_ID:
        ids.add(OWNER_ID)
    return list(ids)


# ───────────────────────── Helpers ─────────────────────────
def esc(s) -> str:
    return html.escape(str(s or ""))


def money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " so'm"


async def main_menu(uid: int) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="📚 Yo'nalishlar"), KeyboardButton(text="📋 Arizalarim")]]
    if await is_admin(uid):
        rows.append([KeyboardButton(text="👮 Admin panel")])
    if uid == OWNER_ID:
        rows.append([KeyboardButton(text="👑 Owner panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


CANCEL_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True
)


async def request_card(req_id: int):
    r = await q(
        """SELECT r.*, u.full_name, u.username, c.title, c.price
           FROM requests r
           LEFT JOIN users u ON u.tg_id = r.user_id
           LEFT JOIN courses c ON c.id = r.course_id
           WHERE r.id=?""",
        (req_id,),
        one=True,
    )
    if not r:
        return None, None
    text = (
        f"📩 <b>Ariza #{r['id']}</b>\n"
        f"👤 {esc(r['full_name'])} "
        f"{'(@' + esc(r['username']) + ')' if r['username'] else ''}\n"
        f"🆔 <code>{r['user_id']}</code>\n"
        f"📚 Kurs: <b>{esc(r['title'])}</b>\n"
        f"🏷 Turi: {KIND_LABEL[r['kind']]}"
    )
    if r["kind"] == "buy":
        text += f"\n💰 Narx: {money(r['price'])}"
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data=f"ok:{r['id']}")
    kb.button(text="❌ Bekor qilish", callback_data=f"no:{r['id']}")
    kb.adjust(2)
    return r, (text, kb.as_markup())


async def send_request_to(bot: Bot, chat_id: int, req_id: int):
    r, card = await request_card(req_id)
    if not r:
        return
    text, kb = card
    if r["file_type"] == "photo":
        await bot.send_photo(chat_id, r["file_id"], caption=text, reply_markup=kb)
    else:
        await bot.send_document(chat_id, r["file_id"], caption=text, reply_markup=kb)


# ───────────────────────── States ─────────────────────────
class Apply(StatesGroup):
    file = State()


class OwnerSt(StatesGroup):
    add_admin = State()
    c_title = State()
    c_price = State()
    c_channel = State()
    bot_text = State()
    bot_photo = State()


# ───────────────────────── Start / umumiy ─────────────────────────
@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    u = m.from_user
    await ex(
        """INSERT INTO users(tg_id, full_name, username) VALUES(?,?,?)
           ON CONFLICT(tg_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username""",
        (u.id, u.full_name, u.username),
    )
    await m.answer(
        f"Assalomu alaykum, <b>{esc(u.full_name)}</b>! 👋\n\n"
        "Bu bot orqali o'quv kurslarimizga arzon narxda yoki bepul shartlar asosida "
        "qo'shilishingiz mumkin.\n\nBoshlash uchun <b>📚 Yo'nalishlar</b> tugmasini bosing.",
        reply_markup=await main_menu(u.id),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Bekor qilish")
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Bekor qilindi.", reply_markup=await main_menu(m.from_user.id))


# ───────────────────────── Foydalanuvchi ─────────────────────────
@router.message(F.text == "📚 Yo'nalishlar")
async def show_courses(m: Message, state: FSMContext):
    await state.clear()
    courses = await q("SELECT * FROM courses WHERE active=1 ORDER BY id")
    if not courses:
        return await m.answer("Hozircha yo'nalishlar mavjud emas.")
    kb = InlineKeyboardBuilder()
    for c in courses:
        kb.button(text=f"{c['title']} — {money(c['price'])}", callback_data=f"course:{c['id']}")
    kb.adjust(1)
    await m.answer("📚 <b>Yo'nalishni tanlang:</b>", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("course:"))
async def course_detail(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    c = await q("SELECT * FROM courses WHERE id=? AND active=1", (cid,), one=True)
    if not c:
        return await cb.answer("Kurs topilmadi", show_alert=True)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"💳 Sotib olish — {money(c['price'])}", callback_data=f"apply:buy:{cid}")
    kb.button(text="♿ Imkoniyati cheklangan (bepul)", callback_data=f"apply:dis:{cid}")
    kb.button(text="🌟 Faol yoshlar (bepul)", callback_data=f"apply:act:{cid}")
    kb.adjust(1)
    await cb.message.answer(
        f"📖 <b>{esc(c['title'])}</b>\n💰 Arzonlashtirilgan narx: <b>{money(c['price'])}</b>\n\n"
        "Qaysi yo'nalish bo'yicha qatnashmoqchisiz?",
        reply_markup=kb.as_markup(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("apply:"))
async def apply_start(cb: CallbackQuery, state: FSMContext):
    _, kind, cid = cb.data.split(":")
    cid = int(cid)
    c = await q("SELECT * FROM courses WHERE id=? AND active=1", (cid,), one=True)
    if not c:
        return await cb.answer("Kurs topilmadi", show_alert=True)

    old = await q(
        "SELECT status FROM requests WHERE user_id=? AND course_id=? "
        "AND status IN ('pending','approved') ORDER BY id DESC",
        (cb.from_user.id, cid),
        one=True,
    )
    if old:
        txt = (
            "Sizning arizangiz allaqachon ko'rib chiqilmoqda ⏳"
            if old["status"] == "pending"
            else "Siz bu kursga allaqachon qabul qilingansiz ✅"
        )
        return await cb.answer(txt, show_alert=True)

    await state.set_state(Apply.file)
    await state.update_data(kind=kind, course_id=cid)

    if kind == "buy":
        text = (
            f"💳 <b>To'lov: {esc(c['title'])}</b>\n\n"
            f"Summa: <b>{money(c['price'])}</b>\n"
            f"Karta: <code>{esc(CARD_NUMBER)}</code>\n"
            f"Egasi: {esc(CARD_OWNER)}\n\n"
            "To'lovni amalga oshirib, <b>chek rasmini (yoki PDF)</b> shu yerga yuboring."
        )
    elif kind == "dis":
        text = (
            "♿ <b>Imkoniyati cheklangan shaxslar uchun bepul</b>\n\n"
            "Nogironlik guvohnomasi yoki tasdiqlovchi hujjatni "
            "(rasm, PDF yoki DOC) yuboring."
        )
    else:
        text = (
            "🌟 <b>Faol yoshlar uchun bepul</b>\n\n"
            "O'qishdagi yuqori natijalaringiz yoki kundalik (Kundalik.com) baholaringiz "
            "<b>rasmini</b> yuboring."
        )
    await cb.message.answer(text, reply_markup=CANCEL_KB)
    await cb.answer()


ALLOWED_MIME = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)


@router.message(Apply.file, F.photo | F.document)
async def apply_file(m: Message, state: FSMContext, bot: Bot):
    if m.document and not (
        (m.document.mime_type or "") in ALLOWED_MIME
        or (m.document.mime_type or "").startswith("image/")
    ):
        return await m.answer("Faqat rasm, PDF yoki DOC/DOCX fayl yuboring.")
    data = await state.get_data()
    if m.photo:
        file_id, ftype = m.photo[-1].file_id, "photo"
    else:
        file_id, ftype = m.document.file_id, "document"

    req_id = await ex(
        "INSERT INTO requests(user_id, course_id, kind, file_id, file_type) VALUES(?,?,?,?,?)",
        (m.from_user.id, data["course_id"], data["kind"], file_id, ftype),
    )
    await state.clear()
    await m.answer(
        f"✅ Arizangiz qabul qilindi (#{req_id}).\n"
        "Admin ko'rib chiqqach, natija shu yerda yuboriladi.",
        reply_markup=await main_menu(m.from_user.id),
    )
    for aid in await all_admin_ids():
        try:
            await bot.send_message(aid, "🔔 Yangi ariza keldi!")
            await send_request_to(bot, aid, req_id)
        except Exception as e:
            logging.warning("Adminga yuborilmadi %s: %s", aid, e)


@router.message(Apply.file)
async def apply_wrong(m: Message):
    await m.answer("Iltimos, rasm yoki fayl (PDF/DOC) yuboring. Chiqish uchun «❌ Bekor qilish».")


@router.message(F.text == "📋 Arizalarim")
async def my_requests(m: Message, state: FSMContext):
    await state.clear()
    rows = await q(
        """SELECT r.id, r.kind, r.status, c.title FROM requests r
           LEFT JOIN courses c ON c.id=r.course_id
           WHERE r.user_id=? ORDER BY r.id DESC LIMIT 15""",
        (m.from_user.id,),
    )
    if not rows:
        return await m.answer("Sizda hali arizalar yo'q.")
    text = "📋 <b>Arizalaringiz:</b>\n\n" + "\n".join(
        f"#{r['id']} · {esc(r['title'])} · {STATUS_LABEL[r['status']]}" for r in rows
    )
    await m.answer(text)


# ───────────────────────── Admin panel ─────────────────────────
@router.message(F.text == "👮 Admin panel")
async def admin_panel(m: Message, state: FSMContext):
    await state.clear()
    if not await is_admin(m.from_user.id):
        return await m.answer("Sizda ruxsat yo'q.")
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Kutilayotgan arizalar", callback_data="adm:pending")
    kb.button(text="📊 Statistika", callback_data="adm:stats")
    kb.adjust(1)
    await m.answer("👮 <b>Admin panel</b>", reply_markup=kb.as_markup())


@router.callback_query(F.data == "adm:pending")
async def adm_pending(cb: CallbackQuery, bot: Bot):
    if not await is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    rows = await q("SELECT id FROM requests WHERE status='pending' ORDER BY id LIMIT 10")
    await cb.answer()
    if not rows:
        return await cb.message.answer("Kutilayotgan arizalar yo'q ✅")
    await cb.message.answer(f"Kutilayotgan arizalar (eng eskilari, {len(rows)} ta):")
    for r in rows:
        await send_request_to(bot, cb.from_user.id, r["id"])


@router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    users = (await q("SELECT COUNT(*) n FROM users", one=True))["n"]
    st = {r["status"]: r["n"] for r in await q("SELECT status, COUNT(*) n FROM requests GROUP BY status")}
    await cb.message.answer(
        f"📊 <b>Statistika</b>\n👥 Foydalanuvchilar: {users}\n"
        f"⏳ Kutilmoqda: {st.get('pending', 0)}\n"
        f"✅ Tasdiqlangan: {st.get('approved', 0)}\n"
        f"❌ Rad etilgan: {st.get('rejected', 0)}"
    )
    await cb.answer()


async def mark_card(cb: CallbackQuery, suffix: str):
    try:
        base = cb.message.caption or ""
        await cb.message.edit_caption(caption=f"{base}\n\n{suffix}", reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("ok:"))
async def approve(cb: CallbackQuery, bot: Bot):
    if not await is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    req_id = int(cb.data.split(":")[1])
    r = await q(
        "SELECT r.*, c.title, c.channel_id FROM requests r JOIN courses c ON c.id=r.course_id WHERE r.id=?",
        (req_id,),
        one=True,
    )
    if not r:
        return await cb.answer("Ariza topilmadi", show_alert=True)
    if r["status"] != "pending":
        await mark_card(cb, f"ℹ️ Allaqachon ko'rib chiqilgan: {STATUS_LABEL[r['status']]}")
        return await cb.answer("Bu ariza allaqachon ko'rib chiqilgan", show_alert=True)
    if not r["channel_id"]:
        return await cb.answer(
            "Bu kurs uchun kanal ID kiritilmagan. Owner panelda kursni kanal bilan qayta qo'shing.",
            show_alert=True,
        )
    try:
        kw = {"chat_id": r["channel_id"], "name": f"req{req_id}"}
        if INVITE_MODE == "single":
            kw.update(member_limit=1, expire_date=int(time.time()) + 48 * 3600)
        link = await bot.create_chat_invite_link(**kw)
    except Exception as e:
        return await cb.answer(
            f"Link yaratib bo'lmadi. Bot kanalga admin ekanini tekshiring.\n{str(e)[:120]}",
            show_alert=True,
        )

    await ex("UPDATE requests SET status='approved', admin_id=? WHERE id=?", (cb.from_user.id, req_id))
    note = "Link bir martalik va 48 soat amal qiladi." if INVITE_MODE == "single" else ""
    try:
        await bot.send_message(
            r["user_id"],
            f"🎉 Arizangiz <b>tasdiqlandi</b>!\n\n📚 Kurs: <b>{esc(r['title'])}</b>\n"
            f"🔗 Yopiq kanalga qo'shilish: {link.invite_link}\n\n{note}",
        )
        sent = "Foydalanuvchiga link yuborildi."
    except Exception:
        sent = "⚠️ Foydalanuvchiga xabar yuborib bo'lmadi (botni bloklagan bo'lishi mumkin)."
    await mark_card(cb, f"✅ Tasdiqlandi — {esc(cb.from_user.full_name)}")
    await cb.answer(sent, show_alert=True)


@router.callback_query(F.data.startswith("no:"))
async def reject(cb: CallbackQuery, bot: Bot):
    if not await is_admin(cb.from_user.id):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    req_id = int(cb.data.split(":")[1])
    r = await q(
        "SELECT r.*, c.title FROM requests r JOIN courses c ON c.id=r.course_id WHERE r.id=?",
        (req_id,),
        one=True,
    )
    if not r:
        return await cb.answer("Ariza topilmadi", show_alert=True)
    if r["status"] != "pending":
        await mark_card(cb, f"ℹ️ Allaqachon ko'rib chiqilgan: {STATUS_LABEL[r['status']]}")
        return await cb.answer("Bu ariza allaqachon ko'rib chiqilgan", show_alert=True)
    await ex("UPDATE requests SET status='rejected', admin_id=? WHERE id=?", (cb.from_user.id, req_id))
    try:
        await bot.send_message(
            r["user_id"],
            f"😔 Afsus, <b>{esc(r['title'])}</b> kursi bo'yicha arizangiz rad etildi.\n"
            "Hujjatlar aniq va to'liq ekanini tekshirib, qaytadan urinib ko'rishingiz mumkin.",
        )
    except Exception:
        pass
    await mark_card(cb, f"❌ Rad etildi — {esc(cb.from_user.full_name)}")
    await cb.answer("Rad etildi")


# ───────────────────────── Owner panel ─────────────────────────
def owner_only(cb_or_msg) -> bool:
    return cb_or_msg.from_user.id == OWNER_ID


@router.message(F.text == "👑 Owner panel")
async def owner_panel(m: Message, state: FSMContext):
    await state.clear()
    if not owner_only(m):
        return await m.answer("Sizda ruxsat yo'q.")
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Admin qo'shish", callback_data="own:addadm")
    kb.button(text="➖ Admin o'chirish", callback_data="own:deladm")
    kb.button(text="📚 Kurs qo'shish", callback_data="own:addcourse")
    kb.button(text="🗑 Kurs o'chirish", callback_data="own:delcourse")
    kb.button(text="🤖 Bot nomi", callback_data="bs:name")
    kb.button(text="📝 Bot tavsifi", callback_data="bs:desc")
    kb.button(text="📄 Qisqa tavsif", callback_data="bs:short")
    kb.button(text="🖼 Bot rasmi", callback_data="bs:photo")
    kb.adjust(2)
    await m.answer("👑 <b>Owner panel</b>", reply_markup=kb.as_markup())


# --- adminlar
@router.callback_query(F.data == "own:addadm")
async def own_addadm(cb: CallbackQuery, state: FSMContext):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    await state.set_state(OwnerSt.add_admin)
    await cb.message.answer("Yangi adminning Telegram ID raqamini yuboring (bekor: /cancel):")
    await cb.answer()


@router.message(OwnerSt.add_admin)
async def own_addadm_id(m: Message, state: FSMContext):
    if not owner_only(m):
        return
    if not (m.text or "").strip().isdigit():
        return await m.answer("ID faqat raqamlardan iborat bo'lishi kerak. Qayta yuboring:")
    aid = int(m.text.strip())
    await ex("INSERT OR IGNORE INTO admins(tg_id) VALUES(?)", (aid,))
    await state.clear()
    await m.answer(f"✅ <code>{aid}</code> admin qilib qo'shildi.")


@router.callback_query(F.data == "own:deladm")
async def own_deladm(cb: CallbackQuery):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    rows = await q("SELECT tg_id FROM admins")
    if not rows:
        await cb.answer()
        return await cb.message.answer("Adminlar yo'q.")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"🗑 {r['tg_id']}", callback_data=f"rmadm:{r['tg_id']}")
    kb.adjust(2)
    await cb.message.answer("Qaysi adminni o'chirasiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("rmadm:"))
async def own_rmadm(cb: CallbackQuery):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    aid = int(cb.data.split(":")[1])
    await ex("DELETE FROM admins WHERE tg_id=?", (aid,))
    await cb.message.edit_text(f"✅ <code>{aid}</code> adminlikdan olindi.")
    await cb.answer()


# --- kurslar
@router.callback_query(F.data == "own:addcourse")
async def own_addcourse(cb: CallbackQuery, state: FSMContext):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    await state.set_state(OwnerSt.c_title)
    await cb.message.answer("Kurs nomini yuboring (bekor: /cancel):")
    await cb.answer()


@router.message(OwnerSt.c_title)
async def own_c_title(m: Message, state: FSMContext):
    if not owner_only(m) or not m.text:
        return
    await state.update_data(title=m.text.strip())
    await state.set_state(OwnerSt.c_price)
    await m.answer("Narxini yuboring (faqat raqam, so'mda):")


@router.message(OwnerSt.c_price)
async def own_c_price(m: Message, state: FSMContext):
    if not owner_only(m):
        return
    t = (m.text or "").replace(" ", "")
    if not t.isdigit():
        return await m.answer("Faqat raqam yuboring:")
    await state.update_data(price=int(t))
    await state.set_state(OwnerSt.c_channel)
    await m.answer(
        "Yopiq kanal ID sini yuboring (masalan <code>-1001234567890</code>).\n"
        "Bot o'sha kanalda admin bo'lishi va «Taklif havolalarini yaratish» huquqiga ega bo'lishi kerak."
    )


@router.message(OwnerSt.c_channel)
async def own_c_channel(m: Message, state: FSMContext):
    if not owner_only(m):
        return
    t = (m.text or "").strip()
    if not t.lstrip("-").isdigit():
        return await m.answer("Kanal ID raqam bo'lishi kerak (masalan -1001234567890):")
    d = await state.get_data()
    await ex(
        "INSERT INTO courses(title, price, channel_id) VALUES(?,?,?)",
        (d["title"], d["price"], int(t)),
    )
    await state.clear()
    await m.answer(f"✅ Kurs qo'shildi: <b>{esc(d['title'])}</b> — {money(d['price'])}")


@router.callback_query(F.data == "own:delcourse")
async def own_delcourse(cb: CallbackQuery):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    rows = await q("SELECT id, title FROM courses WHERE active=1")
    if not rows:
        await cb.answer()
        return await cb.message.answer("Kurslar yo'q.")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"🗑 {r['title']}", callback_data=f"rmc:{r['id']}")
    kb.adjust(1)
    await cb.message.answer("Qaysi kursni o'chirasiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("rmc:"))
async def own_rmc(cb: CallbackQuery):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    cid = int(cb.data.split(":")[1])
    await ex("UPDATE courses SET active=0 WHERE id=?", (cid,))
    await cb.message.edit_text("✅ Kurs o'chirildi.")
    await cb.answer()


# --- bot profili
BOT_PROMPTS = {
    "name": "Yangi bot nomini yuboring (max 64 belgi):",
    "desc": "Yangi tavsifni yuboring (max 512 belgi):",
    "short": "Yangi qisqa tavsifni yuboring (max 120 belgi):",
}


@router.callback_query(F.data.startswith("bs:"))
async def own_bot_settings(cb: CallbackQuery, state: FSMContext):
    if not owner_only(cb):
        return await cb.answer("Ruxsat yo'q", show_alert=True)
    field = cb.data.split(":")[1]
    if field == "photo":
        await state.set_state(OwnerSt.bot_photo)
        await cb.message.answer("Bot uchun yangi rasm yuboring (JPG, kvadrat rasm yaxshi):")
    else:
        await state.set_state(OwnerSt.bot_text)
        await state.update_data(field=field)
        await cb.message.answer(BOT_PROMPTS[field])
    await cb.answer()


@router.message(OwnerSt.bot_text)
async def own_bot_text(m: Message, state: FSMContext, bot: Bot):
    if not owner_only(m) or not m.text:
        return
    field = (await state.get_data())["field"]
    text = m.text.strip()
    try:
        if field == "name":
            await bot.set_my_name(name=text[:64])
        elif field == "desc":
            await bot.set_my_description(description=text[:512])
        else:
            await bot.set_my_short_description(short_description=text[:120])
        await m.answer("✅ Yangilandi. (Telegramda ko'rinishi bir necha daqiqa olishi mumkin.)")
    except Exception as e:
        await m.answer(f"Xatolik: {esc(str(e)[:200])}")
    await state.clear()


@router.message(OwnerSt.bot_photo, F.photo)
async def own_bot_photo(m: Message, state: FSMContext, bot: Bot):
    if not owner_only(m):
        return
    buf = io.BytesIO()
    await bot.download(m.photo[-1], destination=buf)
    try:
        from aiogram.types import InputProfilePhotoStatic

        await bot.set_my_profile_photo(
            photo=InputProfilePhotoStatic(photo=BufferedInputFile(buf.getvalue(), "photo.jpg"))
        )
        await m.answer("✅ Bot rasmi yangilandi.")
    except Exception:
        await m.answer(
            "Rasmni avtomatik o'rnatib bo'lmadi (aiogram versiyasi eski bo'lishi mumkin).\n"
            "Yangilab ko'ring: <code>pip install -U aiogram</code>\n"
            "Yoki @BotFather → /setuserpic orqali o'zgartiring."
        )
    await state.clear()


@router.message(OwnerSt.bot_photo)
async def own_bot_photo_wrong(m: Message):
    await m.answer("Iltimos, rasm yuboring (/cancel — bekor qilish).")


# ───────────────────────── Ishga tushirish ─────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN or not OWNER_ID:
        raise SystemExit(".env faylida BOT_TOKEN va OWNER_ID ni to'ldiring")
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

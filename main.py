import os
import sys
import asyncio
import aiohttp
import time
import html
import re
import uuid
from typing import Optional, List, Tuple, Dict, Any, Set

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.errors import FloodWait
from supabase import create_client, Client as SupabaseClient

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

DRIVERS_GROUP_ID = int(os.getenv("DRIVERS_GROUP_ID", "-1003748433414") or "-1003748433414")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "7748145808") or "7748145808")

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "http://127.0.0.1:8000").strip()

PHONE_NUMBERS_RAW = os.getenv("PHONE_NUMBER", "")
PHONE_NUMBERS_ENV_FALLBACK = [
    p.strip().strip('"').strip("'") for p in (PHONE_NUMBERS_RAW or "").split(",") if p.strip()
]

SEND_WORKERS = int(os.getenv("SEND_WORKERS", "20") or "20")

QUEUE_MAX = int(os.getenv("QUEUE_MAX", "50000") or "50000")

CACHE_TTL = int(os.getenv("CACHE_TTL", "300") or "300")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "1800") or "1800")

# Debug mode - terminalga print chiqishini yoqish/o'chirish
DEBUG = False

# Majburiy obuna guruhi ID (botdan foydalanish uchun a'zo bo'lish shart)
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "-1002188362376").strip()
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK", "https://t.me/+abcdefghijkl").strip()

BLOKEDGRUP_ID_RAW = os.getenv("BLOKEDGRUP_ID", "")
BLOKED_GROUP_IDS = set()
for x in (BLOKEDGRUP_ID_RAW or "").split(","):
    x = x.strip()
    if not x:
        continue
    try:
        BLOKED_GROUP_IDS.add(int(x))
    except Exception:
        pass
BLOKED_GROUP_IDS.add(int(DRIVERS_GROUP_ID))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESS_DIR, exist_ok=True)

supabase: Optional[SupabaseClient] = None

keywords_cache: List[str] = []
keywords_regex = None
last_cache_update = 0.0
_keywords_lock = asyncio.Lock()
_seen_messages: Dict[tuple, float] = {}

watched_groups_cache = set()
account_groups_cache: Dict[str, set] = {}
groups_cache_loaded = False

account_stats: Dict[str, Dict[str, int]] = {}
running_clients: Dict[str, asyncio.Task] = {}
ALL_PHONES: List[str] = []

send_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
aiohttp_session: Optional[aiohttp.ClientSession] = None

# Tasdiqlangan userlar (kontakt ulashganlar)
approved_users: Set[int] = set()
pending_contact: Set[int] = set()  # Kontakt kutilayotgan userlar

_bot_last_update_id: int = 0
_bot_polling_offset: int = 0

_admin_last_notify: Dict[str, float] = {}
ADMIN_NOTIFY_TTL = 120

URL_RE = re.compile(r"(https?://\S+|t\.me/\S+|telegram\.me/\S+)", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """
    Matnni normalizatsiya qilish - Cyrillic harflarini Latin ekvivalentlariga almashtirish.
    Bu 'ОДАМ' (Cyrillic) va 'odam' (Latin) ni bir xil qilib qidirish uchun kerak.
    """
    if not text:
        return text
    
    # Cyrillic -> Latin mapping (look-alike characters)
    cyrillic_to_latin = {
        'а': 'a', 'А': 'A',
        'о': 'o', 'О': 'O',
        'е': 'e', 'Е': 'E',
        'с': 'c', 'С': 'C',
        'х': 'x', 'Х': 'X',
        'р': 'p', 'Р': 'P',
        'у': 'y', 'У': 'Y',
        'к': 'k', 'К': 'K',
        'м': 'm', 'М': 'M',
        'т': 't', 'Т': 'T',
        'в': 'b', 'В': 'B',
        'н': 'n', 'Н': 'N',
        'г': 'g', 'Г': 'G',
        'з': 'z', 'З': 'Z',
        'д': 'd', 'Д': 'D',
        'л': 'l', 'Л': 'L',
        'и': 'i', 'И': 'I',
        'п': 'p', 'П': 'P',
        'р': 'r', 'Р': 'R',
        'с': 's', 'С': 'S',
        'у': 'u', 'У': 'U',
        'ф': 'f', 'Ф': 'F',
        'ц': 'ts', 'Ц': 'Ts',
        'ч': 'ch', 'Ч': 'Ch',
        'ш': 'sh', 'Ш': 'Sh',
        'щ': 'sch', 'Щ': 'Sch',
        'ъ': '', 'Ъ': '',
        'ы': 'y', 'Ы': 'Y',
        'ь': '', 'Ь': '',
        'э': 'e', 'Э': 'E',
        'ю': 'yu', 'Ю': 'Yu',
        'я': 'ya', 'Я': 'Ya',
        'ў': 'o', 'Ў': 'O',
        'қ': 'q', 'Қ': 'Q',
        'ғ': 'g', 'Ғ': 'G',
        'ҳ': 'h', 'Ҳ': 'H',
        'ҷ': 'j', 'Ҷ': 'J',
    }
    
    result = []
    for char in text:
        if char in cyrillic_to_latin:
            result.append(cyrillic_to_latin[char])
        else:
            result.append(char)
    return ''.join(result)


def normalize_chat_id(chat_id: int) -> int:
    try:
        return int(chat_id)
    except Exception:
        return chat_id


BLOKED_GROUP_IDS_NORM = {normalize_chat_id(x) for x in (BLOKED_GROUP_IDS or set())}


def _normalize_phone(p: str) -> str:
    return (p or "").strip().replace(" ", "")


def uniq_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def init_supabase() -> bool:
    global supabase
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ SUPABASE_URL yoki SUPABASE_SERVICE_KEY .env da yo‘q")
            return False
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase ulandi")
        return True
    except Exception as e:
        print(f"❌ Supabase ulanishda xato: {e}")
        return False


async def notify_admin_once(key: str, text: str):
    global aiohttp_session, _admin_last_notify
    if not BOT_TOKEN or not ADMIN_ID or not aiohttp_session:
        return

    now = time.time()
    last = _admin_last_notify.get(key, 0)
    if now - last < ADMIN_NOTIFY_TTL:
        return
    _admin_last_notify[key] = now

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_ID, "text": text}
    try:
        async with aiohttp_session.post(url, json=payload, timeout=20) as resp:
            await resp.text()
    except Exception:
        pass


async def send_bot_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Bot orqali xabar yuborish (yordamchi funksiya)"""
    global aiohttp_session
    if not BOT_TOKEN or not aiohttp_session:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        async with aiohttp_session.post(url, json=payload, timeout=20) as resp:
            return resp.status == 200
    except Exception:
        return False


async def check_user_subscription(user_id: int) -> bool:
    """User majburiy kanal/guruhga a'zomi tekshirish"""
    if not BOT_TOKEN or not aiohttp_session or not REQUIRED_CHANNEL_ID:
        return True
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
    payload = {"chat_id": int(REQUIRED_CHANNEL_ID), "user_id": user_id}
    try:
        async with aiohttp_session.post(url, json=payload, timeout=20) as resp:
            if resp.status == 200:
                j = await resp.json()
                if j.get("ok"):
                    status = j.get("result", {}).get("status", "")
                    # 'left' va 'kicked' holatlari tashqari barchasi a'zolik
                    return status not in ("left", "kicked")
            return False
    except Exception:
        return False


async def send_subscription_request(chat_id: int) -> bool:
    """Majburiy obuna xabarini yuborish"""
    text = (
        "📢 <b>Botdan foydalanish uchun obuna bo'lish shart!</b>\n\n"
        "Iltimos, quyidagi tugmani bosib guruhimizga a'zo bo'ling.\n"
        "A'zo bo'lganingizdan keyin /start buyrug'ini qayta yuboring."
    )
    if not BOT_TOKEN or not aiohttp_session:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "📢 Guruhga obuna bo'lish", "url": REQUIRED_CHANNEL_LINK}
            ]]
        }
    }
    try:
        async with aiohttp_session.post(url, json=payload, timeout=20) as resp:
            return resp.status == 200
    except Exception:
        return False


async def require_subscription(chat_id: int, user_id: int) -> bool:
    """Bot buyruqlari uchun obuna tekshiruvi"""
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_request(chat_id)
        return False
    return True


async def load_approved_users():
    """Bazadan tasdiqlangan userlarni yuklash"""
    global approved_users
    if not supabase:
        return
    try:
        result = await sb_execute(lambda: supabase.table("approved_users").select("user_id").execute())
        data = getattr(result, "data", None) or []
        approved_users = {int(row["user_id"]) for row in data}
        print(f"✅ Tasdiqlangan userlar yuklandi: {len(approved_users)} ta")
    except Exception as e:
        print(f"⚠️ approved_users yuklashda xato: {e}")


async def save_approved_user(user_id: int, phone: str = None, username: str = None):
    """Tasdiqlangan userni bazaga saqlash"""
    if not supabase:
        return False
    try:
        await sb_execute(lambda: supabase.table("approved_users").insert({
            "user_id": user_id,
            "phone": phone,
            "username": username,
        }).execute())
        approved_users.add(user_id)
        return True
    except Exception as e:
        print(f"⚠️ approved_user saqlashda xato: {e}")
        return False


async def handle_start_command(chat_id: int, user_id: int, username: str = None):
    """/start komandasini qayta ishlash"""
    global pending_contact

    # Admin obuna tekshiruvidan ozod
    if user_id != ADMIN_ID:
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            await send_subscription_request(chat_id)
            return
    
    # Admin uchun statistika
    if user_id == ADMIN_ID:
        phones_list = ALL_PHONES or list(running_clients.keys()) or PHONE_NUMBERS_ENV_FALLBACK
        total_groups = 0
        total_active = 0
        active_accounts = 0

        for phone in phones_list:
            stats = account_stats.get(phone, {})
            total = int(stats.get("groups_count", 0) or 0)
            active = int(stats.get("active_count", 0) or 0)
            total_groups += total
            total_active += active
            if total > 0:
                active_accounts += 1

        status_text = (
            f"📊 <b>ADMIN PANEL</b>\n"
            f"{'=' * 30}\n\n"
            f"📱 <b>Akkauntlar:</b> {len(phones_list)} ta\n"
            f"   └ Faol: {active_accounts} ta\n\n"
            f"👥 <b>Guruhlar:</b>\n"
            f"   └ Jami: {total_groups} ta\n"
            f"   └ Faol: {total_active} ta\n\n"
            f"🚫 <b>Bloklangan:</b> {len(BLOKED_GROUP_IDS_NORM)} ta\n"
            f"💾 <b>Keshda:</b> {len(watched_groups_cache)} ta\n\n"
            f"🔑 <b>Kalit so'zlar:</b> {len(keywords_cache)} ta\n"
            f"👤 <b>Tasdiqlangan userlar:</b> {len(approved_users)} ta\n"
            f"⏱ <b>Yangilanish:</b> {CACHE_TTL // 60} daqiqa\n"
        )
        await send_bot_message(chat_id, status_text)
        return
    
    # Oddiy user uchun
    if user_id in approved_users:
        await send_bot_message(
            chat_id,
            "👋 Salom! Siz allaqachon tasdiqlangan siz.\n\n"
            "💡 <b>Foydalanish:</b>\n"
            "<code>/user {telegram_id}</code> - User ma'lumotlarini ko'rish\n\n"
            "Masalan: <code>/user 7748145808</code>"
        )
        return
    
    # Kontakt kutilayotgan user
    if user_id in pending_contact:
        await send_bot_message(
            chat_id,
            "⏳ Iltimos, quyidagi tugmani bosib kontaktingizni ulashing.\n"
            "Bu faqat bir marta so'raladi va xavfsiz saqlanadi."
        )
        return
    
    # Yangi user - kontakt so'rash
    pending_contact.add(user_id)
    await send_bot_message(
        chat_id,
        "👋 <b>Salom!</b>\n\n"
        "Botdan foydalanish uchun kontakt ma'lumotlaringizni ulashing.\n"
        "Bu <b>faqat bir marta</b> so'raladi va xavfsiz saqlanadi.\n\n"
        "⬇️ Quyidagi tugmani bosing:",
        reply_markup={
            "keyboard": [[{"text": "📱 Kontaktni ulashish", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
    )


async def handle_contact(message: dict):
    """Kontakt ulashishni qayta ishlash"""
    global pending_contact, approved_users
    
    user_id = message.get("from", {}).get("id", 0)
    chat_id = message.get("chat", {}).get("id", 0)
    contact = message.get("contact")
    
    if not contact:
        return
    
    # Kontakt userning o'zi kontaktimi tekshirish
    contact_user_id = contact.get("user_id")
    if contact_user_id and contact_user_id != user_id:
        await send_bot_message(chat_id, "❌ Faqat o'zingizning kontaktingizni ulashing.")
        return
    
    # Tasdiqlash
    phone = contact.get("phone_number", "")
    username = message.get("from", {}).get("username", "")
    
    # Bazaga saqlash
    await save_approved_user(user_id, phone, username)
    
    # Set dan o'chirish va approved ga qo'shish
    if user_id in pending_contact:
        pending_contact.remove(user_id)
    approved_users.add(user_id)
    
    # Klaviaturani olib tashlash va tasdiqlash xabari
    await send_bot_message(
        chat_id,
        "✅ <b>Tasdiqlandi!</b>\n\n"
        "Endi siz /user buyrug'i orqali user ma'lumotlarini ko'rishingiz mumkin.\n\n"
        "💡 <b>Foydalanish:</b>\n"
        "<code>/user {telegram_id}</code>\n\n"
        "Masalan: <code>/user 7748145808</code>",
        reply_markup={"remove_keyboard": True}
    )


async def handle_user_lookup(chat_id: int, user_id: int, text: str):
    """/user {id} komandasi - user ma'lumotlarini ko'rsatish"""
    # Majburiy obuna tekshiruvi
    if user_id != ADMIN_ID:
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            await send_subscription_request(chat_id)
            return
    
    # Admin yoki tasdiqlangan userlar uchun ruxsat
    if user_id != ADMIN_ID and user_id not in approved_users:
        await send_bot_message(
            chat_id, 
            "⛔ <b>Ruxsat yo'q!</b>\n\n"
            "Avval <code>/start</code> buyrug'ini bosing va kontakt ulashing.\n"
            "Tasdiqlangan userlar /user buyrug'idan foydalanishi mumkin."
        )
        return

    # Parse command: /user 123456789
    parts = text.strip().split()
    if len(parts) < 2:
        await send_bot_message(
            chat_id,
            "📋 <b>User ma'lumotlari</b>\n\n"
            "Foydalanish: <code>/user {ID}</code>\n"
            "Masalan: <code>/user 7748145808</code>\n\n"
            "Bu komanda user haqida bazadan ma'lumot olish uchun ishlatiladi."
        )
        return

    target_id = parts[1]
    if not target_id.isdigit():
        await send_bot_message(chat_id, "❌ ID faqat raqam bo'lishi kerak. Masalan: <code>/user 123456789</code>")
        return

    # Search in captured_messages for this user
    if not supabase:
        await send_bot_message(chat_id, "❌ Bazaga ulanish yo'q.")
        return

    try:
        # Look for messages from this user by sender_link (tg://user?id=...)
        sender_link = f"tg://user?id={target_id}"
        result = await sb_execute(
            lambda: supabase.table("captured_messages")
            .select("*")
            .eq("sender_link", sender_link)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        
        data = getattr(result, "data", None) or []
        
        if not data:
            # Fallback: search in text content
            result = await sb_execute(
                lambda: supabase.table("captured_messages")
                .select("*")
                .ilike("text", f"%🆔 ID: <code>{target_id}</code>%")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            data = getattr(result, "data", None) or []

        if not data:
            await send_bot_message(
                chat_id,
                f"ℹ️ User <code>{target_id}</code> haqida ma'lumot topilmadi.\n\n"
                f"🔍 Bazada ushbu ID bilan xabarlar yo'q.\n"
                f"💡 User hali kalit so'z yozmagan bo'lishi mumkin."
            )
            return

        # Build response
        response = f"👤 <b>User ma'lumotlari</b>\n🆔 ID: <code>{target_id}</code>\n\n"
        response += f"📨 <b>So'ngi xabarlar ({len(data)} ta):</b>\n\n"
        
        for idx, msg in enumerate(data, 1):
            group_name = msg.get("group_name", "Noma'lum guruh")
            text_preview = (msg.get("text", "") or "")[:100]
            keyword = msg.get("keyword", "N/A")
            created = msg.get("created_at", "N/A")
            
            response += (
                f"{idx}. 📍 <b>{html.escape(group_name)}</b>\n"
                f"   🔑 Kalit so'z: {keyword}\n"
                f"   📝 {html.escape(text_preview)}...\n"
                f"   ⏰ {created}\n\n"
            )

        # Add action buttons
        user_link = f"tg://user?id={target_id}"
        response += (
            f"🔗 <b>Actions:</b>\n"
            f"• <a href=\"{user_link}\">Telegram orqali ochish</a> (agar ochilsa)\n"
            f"• Bot orqali yozish: <code>/msg {target_id} salom</code>\n"
        )

        await send_bot_message(chat_id, response)

    except Exception as e:
        print(f"❌ User lookup xato: {e}")
        await send_bot_message(chat_id, f"❌ Xatolik yuz berdi: {e}")


async def handle_groups_command(chat_id: int, user_id: int):
    """/groups komandasi - kuzatilayotgan guruhlarni ko'rsatish"""
    # Majburiy obuna tekshiruvi
    if user_id != ADMIN_ID:
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            await send_subscription_request(chat_id)
            return
    
    if user_id != ADMIN_ID:
        await send_bot_message(chat_id, "⛔ Sizga ruxsat yo'q.")
        return

    if not supabase:
        await send_bot_message(chat_id, "❌ Bazaga ulanish yo'q.")
        return

    try:
        # Get all groups from database
        result = await sb_execute(
            lambda: supabase.table("account_groups")
            .select("phone_number, group_id, group_name")
            .execute()
        )
        
        data = getattr(result, "data", None) or []
        
        if not data:
            await send_bot_message(chat_id, "📭 Kuzatilayotgan guruhlar topilmadi.")
            return

        # Group by phone number
        groups_by_phone = {}
        for row in data:
            phone = row.get("phone_number", "N/A")
            group_name = row.get("group_name", "Noma'lum")
            group_id = row.get("group_id", "N/A")
            if phone not in groups_by_phone:
                groups_by_phone[phone] = []
            groups_by_phone[phone].append((group_name, group_id))

        # Build response
        response = "📋 <b>KUZATILAYOTGAN GURUHLAR</b>\n"
        response += f"{'=' * 30}\n\n"
        
        for phone, groups in groups_by_phone.items():
            response += f"📱 <code>{phone}</code> ({len(groups)} ta)\n"
            for idx, (name, gid) in enumerate(groups[:10], 1):  # Show first 10
                username_info = ""
                if isinstance(gid, int):
                    # Check if in blocked list
                    if normalize_chat_id(gid) in BLOKED_GROUP_IDS_NORM:
                        username_info = " 🚫 BLOK"
                response += f"   {idx}. {html.escape(name[:30])}{username_info}\n"
            if len(groups) > 10:
                response += f"   ... va yana {len(groups) - 10} ta\n"
            response += "\n"

        response += f"💡 Jami: {len(data)} ta guruh/kanal\n"
        response += f"💡 Tekshirish: https://t.me/DinurA380 kabi guruhlarni qidiring"

        await send_bot_message(chat_id, response)

    except Exception as e:
        print(f"❌ Groups command xato: {e}")
        await send_bot_message(chat_id, f"❌ Xatolik yuz berdi: {e}")


async def bot_polling_loop():
    """Bot komandalarini polling orqali qayta ishlash"""
    global _bot_polling_offset, aiohttp_session
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN yo'q, bot polling ishga tushmaydi")
        return

    print("🤖 Bot polling ishga tushdi...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    while True:
        try:
            if not aiohttp_session:
                await asyncio.sleep(5)
                continue

            params = {"offset": _bot_polling_offset, "limit": 10, "timeout": 30}
            async with aiohttp_session.get(url, params=params, timeout=35) as resp:
                if resp.status != 200:
                    await asyncio.sleep(5)
                    continue

                data = await resp.json()
                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                updates = data.get("result", [])
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id >= _bot_polling_offset:
                        _bot_polling_offset = update_id + 1

                    # Message tekshirish
                    message = update.get("message")
                    if message:
                        text = message.get("text", "")
                        chat_id = message.get("chat", {}).get("id", 0)
                        user_id = message.get("from", {}).get("id", 0)
                        username = message.get("from", {}).get("username", "")
                        text_lower = text.strip().lower() if text else ""

                        # Contact ulashish tekshirish
                        if message.get("contact"):
                            await handle_contact(message)
                            continue

                        if text_lower == "/start":
                            await handle_start_command(chat_id, user_id, username)
                        elif text_lower.startswith("/user"):
                            await handle_user_lookup(chat_id, user_id, text)
                        elif text_lower == "/groups":
                            await handle_groups_command(chat_id, user_id)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"⚠️ Bot polling xato: {e}")
            await asyncio.sleep(5)


def session_base_for_phone(phone: str) -> str:
    clean = phone.replace("+", "").replace(" ", "")
    return os.path.join(SESS_DIR, f"userbot_{clean}")


async def safe_delete_session_files(session_base: str, tries: int = 8) -> bool:
    paths = [f"{session_base}.session", f"{session_base}.session-journal"]
    ok_any = False

    for _ in range(tries):
        all_done = True
        for p in paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    ok_any = True
                except PermissionError:
                    all_done = False
                except OSError:
                    all_done = False
        if all_done:
            return ok_any
        await asyncio.sleep(0.6)

    return ok_any



def extract_text_and_urls(message: Message) -> Tuple[str, List[str], str]:
    """
    Extracts text and URLs.
    Now preserves HTML formatting for the main text!
    """
    raw_text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    
    # Generate HTML with entities preserved
    if raw_text:
        if entities:
            # We want to preserve the original formatting (text mentions/links)
            # but we also want to avoid huge spam blocks.
            # Pyrogram provides `.text.html` or `.caption.html` if we access it via the object, 
            # BUT message.text is just a string. 
            # We rely on message.text.html property from pyrogram if available, 
            # otherwise simplistic replacement.
            # However, `message` IS a pyrogram Message object, so it has .text and .caption attributes 
            # which are strings, but the Message object itself usually has helpers.
            # actually message.text is a string. `message.text.html` is not valid.
            # wait, Pyrogram *does* provide `message.text.html` if using `client.get_messages`? 
            # No, `message.text` is a str.
            # Correct way: use `message.text.html` is WRONG.
            # Correct way: Manually rebuild HTML from entities.
            
            # Since manually rebuilding is complex (nested entities), let's see if we can use 
            # a simple approach: Just escape it and let it be plain text? 
            # NO, the user explicitely complained that links (blue text) are lost.
            # We MUST rebuild the HTML.
            
            # Fortunately, Pyrogram's `Message` object usually has a `.text` property which is a string.
            # But recent Pyrogram versions MIGHT have a utility or we write one.
            # Let's write a simple entity-to-html converter.
            
            # ALGORITHM: Sort entities by offset. Insert tags.
            # But wait, `main.py` imports `html`.
            # Let's use a simpler heuristic for now: 
            # Since likely the only important ones are TEXT_LINK and MENTION.
            
            # Actually, the userbot simply forwards the text. 
            # If we just do `message.text.html` (if supported in pyrogram's custom Str object) that would be great.
            # Pyrogram's documentation says `message.text` is a string.
            # BUT, we can use `message.text.markdown` or similar if we use a specific parser? No.
            
            # Alternative: Assume we can construct a basic HTML string.
            # Or use `unparse` from pyrogram? No, that's internal.
            
            # Let's fallback to: Just return escaped raw text if we can't easily parse.
            # BUT wait, the user complaint is "Ko'k yozuv" (blue text) -> Text Link.
            # If we strip links, we lose the URL.
            # We MUST rebuild it.
            
            # Let's implement a basic builder.
            final_text = ""
            last_offset = 0
            
            # Sort entities just in case
            sorted_ents = sorted(entities, key=lambda e: e.offset)
            
            current_text_idx = 0
            built_text = []
            
            # Use raw_text as source
            # This is a naive implementation that doesn't handle overlapping (nested) entities correctly
            # but Telegram usually doesn't allow overlapping entities except for specific cases.
            
            # If this is too risky, we can just use `raw_text` and assume the driver's client 
            # will regex-match URLs. But `Text Link` (hidden URL) won't show.
            
            # Let's try to preserve AT LEAST the Text Links and Mentions.
            
            for ent in sorted_ents:
                if ent.offset < current_text_idx:
                    continue # Skip overlap
                
                # Append text before entity
                built_text.append(html.escape(raw_text[current_text_idx:ent.offset]))
                
                chunk = raw_text[ent.offset : ent.offset + ent.length]
                escaped_chunk = html.escape(chunk)
                
                if ent.type == MessageEntityType.TEXT_LINK:
                    built_text.append(f'<a href="{html.escape(ent.url, quote=True)}">{escaped_chunk}</a>')
                elif ent.type == MessageEntityType.URL:
                    built_text.append(f'<a href="{html.escape(chunk, quote=True)}">{escaped_chunk}</a>')
                elif ent.type == MessageEntityType.BOLD:
                    built_text.append(f'<b>{escaped_chunk}</b>')
                elif ent.type == MessageEntityType.ITALIC:
                    built_text.append(f'<i>{escaped_chunk}</i>')
                elif ent.type == MessageEntityType.CODE:
                    built_text.append(f'<code>{escaped_chunk}</code>')
                elif ent.type == MessageEntityType.TEXT_MENTION and ent.user:
                     # Mention with User object
                     built_text.append(ent.user.mention(chunk, style="html"))
                else:
                    built_text.append(escaped_chunk)
                
                current_text_idx = ent.offset + ent.length
            
            # Append remaining
            built_text.append(html.escape(raw_text[current_text_idx:]))
            final_text = "".join(built_text)

        else:
            final_text = html.escape(raw_text)
    else:
        # No text (media only)
        final_text = ""

    # Extract URLs for the button/logic (legacy logic kept for compatibility)
    urls: List[str] = []
    if entities:
        for ent in entities:
             if ent.type == MessageEntityType.URL:
                 urls.append(raw_text[ent.offset: ent.offset + ent.length])
             elif ent.type == MessageEntityType.TEXT_LINK and getattr(ent, "url", None):
                 urls.append(ent.url)
    
    urls.extend(URL_RE.findall(raw_text))
    urls = uniq_keep_order([u.strip() for u in urls if u and u.strip()])
    
    # Clean logic: We don't want to strip links from the DISPLAY text anymore 
    # because that breaks text mentions. We just want to check keywords.
    # So we return: (html_text, urls, raw_plain_text)
    
    if not final_text:
        has_media = bool(
            message.photo or message.video or message.document or message.audio or
            message.voice or message.video_note or message.animation or message.sticker
        )
        final_text = "📎 Media post" if has_media else "📩 Xabar"

    return final_text, urls, raw_text


def get_message_link(message: Message) -> str:
    chat = message.chat
    msg_id = message.id
    if chat.username:
        return f"https://t.me/{chat.username}/{msg_id}"
    clean_id = str(chat.id).replace("-100", "")
    return f"https://t.me/c/{clean_id}/{msg_id}"


def get_chat_link(message: Message) -> str:
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}"
    # Private group logic
    return get_message_link(message)


def build_sender_anchor(message: Message) -> Tuple[str, Optional[str], str, str]:
    """
    returns:
      sender_html: HTML text with link
      sender_url: URL for button (if valid)
      sender_plain: Plain text name
      sender_info: Additional info (user ID for tracking anonymous users)
    """
    if message.from_user:
        u = message.from_user
        
        name = f"@{u.username}" if u.username else (u.first_name or "User")
        # Always build HTML manually to ensure proper quoting
        url = f"https://t.me/{u.username}" if u.username else f"tg://user?id={u.id}"
        sender_html = f'<a href="{html.escape(url, quote=True)}">{html.escape(name)}</a>'
        
        # Add user ID info for tracking (especially for anonymous/hidden users)
        user_id_str = str(u.id)
        if u.username:
            sender_info = f"@{u.username} | ID: <code>{user_id_str}</code>"
        else:
            sender_info = f"{name} | ID: <code>{user_id_str}</code> ⚠️ Username yo'q"
        
        sender_plain = name
        sender_url = url
        return sender_html, sender_url, sender_plain, sender_info

    if getattr(message, "sender_chat", None):
        sc = message.sender_chat
        title = sc.title or "Sender"
        chat_id_str = str(sc.id)
        
        sender_plain = title
        if sc.username:
            url = f"https://t.me/{sc.username}"
            sender_html = f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
            sender_info = f"@{sc.username} | Chat ID: <code>{chat_id_str}</code>"
            return sender_html, url, sender_plain, sender_info
        else:
            # Private group/channel sender
            sender_html = html.escape(title)
            sender_info = f"{title} | Chat ID: <code>{chat_id_str}</code>"
            return sender_html, None, sender_plain, sender_info

    return "Noma'lum", None, "Noma'lum", "Noma'lum"


async def sb_execute(fn, *args, **kwargs):
    """supabase sync execute() ni event-loop blok qilmasdan bajarish"""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def refresh_keywords():
    global keywords_cache, keywords_regex, last_cache_update
    if not supabase:
        return
    async with _keywords_lock:
        # Double-check inside lock to avoid redundant refreshes
        if time.time() - last_cache_update <= CACHE_TTL:
            return
        try:
            result = await sb_execute(lambda: supabase.table("keywords").select("keyword").execute())
            data = getattr(result, "data", None) or []
            # Normalizatsiya: Cyrillic -> Latin (ОДАМ -> odam)
            keywords_cache = [normalize_text(k["keyword"].lower()) for k in data if k.get("keyword")]
            last_cache_update = time.time()

            if keywords_cache:
                keywords_regex = re.compile(
                    "|".join(re.escape(k) for k in sorted(keywords_cache, key=len, reverse=True)),
                    re.IGNORECASE
                )
            else:
                keywords_regex = None

            print(f"✅ Kalit so'zlar yangilandi: {len(keywords_cache)} ta (normalized)")
        except Exception as e:
            print(f"❌ Kalit so'zlar yangilashda xato: {e}")


async def periodic_keywords_refresh():
    while True:
        await asyncio.sleep(CACHE_TTL)
        await refresh_keywords()


async def save_keyword_hit(keyword: str, group_id: int, group_name: str, phone: str, message_text: str):
    if not supabase:
        return
    try:
        preview = (message_text or "")[:200]
        await sb_execute(lambda: supabase.table("keyword_hits").insert({
            "keyword_id": None,
            "group_id": group_id,
            "group_name": group_name,
            "phone_number": phone,
            "message_preview": preview,
        }).execute())
    except Exception:
        pass


async def save_captured_message(
    cap_id: str,
    phone: str,
    group_id: int,
    group_name: str,
    message_id: int,
    sender_name: str,
    sender_link: str,
    message_link: str,
    text: str,
    urls: list,
    keyword: str
) -> bool:
    """
    captured_messages jadvaliga yozadi. cap_id ni o'zimiz uuid qilib beramiz.
    """
    if not supabase:
        return False
    try:
        await sb_execute(lambda: supabase.table("captured_messages").insert({
            "id": cap_id,
            "phone_number": phone,
            "group_id": int(group_id),
            "group_name": group_name,
            "message_id": int(message_id),
            "sender_name": sender_name,
            "sender_link": sender_link,
            "message_link": message_link,
            "text": text,
            "urls": urls or [],
            "keyword": keyword,
        }).execute())
        return True
    except Exception as e:
        print(f"⚠️ captured_messages insert xato: {e}")
        return False


async def load_groups_cache():
    global watched_groups_cache, account_groups_cache, groups_cache_loaded
    if groups_cache_loaded or not supabase:
        return
    try:
        result = await sb_execute(lambda: supabase.table("watched_groups").select("group_id").execute())
        data = getattr(result, "data", None) or []
        watched_groups_cache = {row["group_id"] for row in data}
        print(f"✅ Kesh yuklandi: {len(watched_groups_cache)} ta guruh bazada mavjud")

        acc_result = await sb_execute(lambda: supabase.table("account_groups").select("phone_number, group_id").execute())
        acc_data = getattr(acc_result, "data", None) or []
        for row in acc_data:
            phone = row.get("phone_number")
            gid = row.get("group_id")
            if phone and gid:
                account_groups_cache.setdefault(phone, set()).add(gid)

        groups_cache_loaded = True
    except Exception as e:
        print(f"⚠️ Kesh yuklashda xato: {e}")


async def sync_account_groups(phone: str, groups: list):
    if not supabase:
        return
    try:
        existing_ids = account_groups_cache.get(phone, set())
        new_groups = [g for g in groups if g["group_id"] not in existing_ids]
        if not new_groups:
            return

        for group in new_groups:
            _g = group  # capture by value to avoid lambda closure bug
            try:
                await sb_execute(lambda _g=_g: supabase.table("account_groups").insert({
                    "phone_number": phone,
                    "group_id": _g["group_id"],
                    "group_name": _g["group_name"],
                }).execute())
                account_groups_cache.setdefault(phone, set()).add(_g["group_id"])
            except Exception:
                pass

        print(f"📝 [{phone}] {len(new_groups)} ta yangi guruh qo'shildi")
    except Exception as e:
        print(f"⚠️ Guruhlarni saqlashda xato: {e}")


async def sync_all_groups(client: Client, phone: str) -> list:
    global watched_groups_cache, account_stats
    if not supabase:
        return []
    try:
        groups_found = []
        channels_found = []

        try:
            async for dialog in client.get_dialogs():
                chat = dialog.chat
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    groups_found.append({
                        "group_id": chat.id,
                        "group_name": chat.title or f"Guruh {chat.id}",
                        "username": getattr(chat, "username", None)
                    })
                elif chat.type == ChatType.CHANNEL:
                    channels_found.append({
                        "group_id": chat.id,
                        "group_name": chat.title or f"Kanal {chat.id}",
                        "username": getattr(chat, "username", None)
                    })
        except FloodWait as fw:
            wait_s = int(getattr(fw, "value", 0) or 0)
            await asyncio.sleep(wait_s + 1)
            async for dialog in client.get_dialogs():
                chat = dialog.chat
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    groups_found.append({
                        "group_id": chat.id,
                        "group_name": chat.title or f"Guruh {chat.id}",
                        "username": getattr(chat, "username", None)
                    })
                elif chat.type == ChatType.CHANNEL:
                    channels_found.append({
                        "group_id": chat.id,
                        "group_name": chat.title or f"Kanal {chat.id}",
                        "username": getattr(chat, "username", None)
                    })

        # Debug: Ko'rinayotgan guruh va kanallar
        all_found = groups_found + channels_found
        usernames = [g.get("username") for g in all_found if g.get("username")]
        print(f"🔍 [{phone}] Topildi: {len(groups_found)} guruh, {len(channels_found)} kanal")
        if usernames:
            print(f"   Usernames: {', '.join(usernames[:10])}{'...' if len(usernames) > 10 else ''}")

        await sync_account_groups(phone, all_found)

        for g in all_found:
            if g["group_id"] in watched_groups_cache:
                continue
            try:
                is_blocked = normalize_chat_id(g["group_id"]) in BLOKED_GROUP_IDS_NORM
                _g = g  # capture by value to avoid lambda closure bug
                _is_blocked = is_blocked
                await sb_execute(lambda _g=_g, _is_blocked=_is_blocked: supabase.table("watched_groups").insert({
                    "group_id": _g["group_id"],
                    "group_name": _g["group_name"],
                    "is_blocked": _is_blocked
                }).execute())
                watched_groups_cache.add(g["group_id"])
            except Exception:
                pass

        active_groups = [
            g for g in groups_found
            if normalize_chat_id(g["group_id"]) not in BLOKED_GROUP_IDS_NORM
        ]
        account_stats[phone] = {"groups_count": len(groups_found), "active_count": len(active_groups)}
        return groups_found
    except Exception as e:
        print(f"❌ [{phone}] Guruhlarni sinxronlashda xato: {e}")
        return []


def print_statistics():
    global account_stats, watched_groups_cache, ALL_PHONES
    print("\n" + "=" * 60)
    print("📊 USERBOT STATISTIKASI")
    print("=" * 60)

    total_groups_all = 0
    total_active_all = 0

    phones_list = ALL_PHONES or list(running_clients.keys()) or PHONE_NUMBERS_ENV_FALLBACK
    print(f"\n📱 AKKAUNTLAR ({len(phones_list)} ta):")
    print("-" * 40)

    for phone in phones_list:
        stats = account_stats.get(phone, {})
        total = int(stats.get("groups_count", 0) or 0)
        active = int(stats.get("active_count", 0) or 0)
        total_groups_all += total
        total_active_all += active
        print(f"  {phone}: {total} guruh, {active} ta faol kuzatilmoqda")

    print("-" * 40)
    print(f"  JAMI: {total_groups_all} guruh, {total_active_all} ta faol kuzatilmoqda")
    print(f"\n🚫 Bloklangan group_id lar: {sorted(list(BLOKED_GROUP_IDS_NORM))}")
    print(f"💾 Keshda: {len(watched_groups_cache)} ta guruh")
    print("=" * 60 + "\n")


async def send_to_drivers_group(
    text: str,
    group_link: str,
    message_link: str,
    extra_urls: Optional[List[str]] = None,
    sender_url: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None
) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    keyboard = []
    # Bot API only supports http/https URLs for inline keyboard buttons
    # tg://user?id=... scheme doesn't work in keyboard buttons
    if sender_url and sender_url.startswith("https://"):
        keyboard.append([{"text": "👤 Клент личкаси", "url": sender_url}])

    keyboard.append([
        {"text": "👥 Guruhga o'tish", "url": group_link},
        {"text": "🔗 Xabarga o'tish", "url": message_link},
    ])

    extra_urls = uniq_keep_order(extra_urls or [])[:3]
    for i, u in enumerate(extra_urls, 1):
        keyboard.append([{"text": f"🔗 Link {i}", "url": u}])

    payload = {
        "chat_id": DRIVERS_GROUP_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard},
    }

    own_session = False
    if session is None:
        session = aiohttp.ClientSession()
        own_session = True

    try:
        for _ in range(8):
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    return True

                if resp.status == 429:
                    retry_after = 3
                    try:
                        j = await resp.json()
                        retry_after = int(j.get("parameters", {}).get("retry_after", retry_after))
                    except Exception:
                        pass
                    await asyncio.sleep(retry_after + 1)
                    continue

                body = await resp.text()
                print(f"❌ Xabar yuborishda xato ({resp.status}): {body}")
                # Debug: problematic text
                if resp.status == 400 and "parse entities" in body:
                    print(f"🔍 DEBUG: Matn uzunligi: {len(text)}")
                    print(f"🔍 DEBUG: Matn (birinch 200 belgi): {text[:200]!r}")
                return False
    except Exception as e:
        print(f"❌ Xabar yuborishda xato: {e}")
        return False
    finally:
        if own_session:
            await session.close()


async def send_worker(worker_id: int):
    global aiohttp_session
    while True:
        item = await send_queue.get()
        try:
            cache_key, forward_text, group_link, message_link, urls, sender_url = item
            ok = await send_to_drivers_group(
                forward_text,
                group_link=group_link,
                message_link=message_link,
                extra_urls=urls,
                sender_url=sender_url,
                session=aiohttp_session
            )
            if not ok:
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"⚠️ send_worker[{worker_id}] xato: {e}")
        finally:
            send_queue.task_done()


async def ensure_accounts_seeded_from_env():
    if not supabase or not PHONE_NUMBERS_ENV_FALLBACK:
        return
    try:
        existing = await sb_execute(lambda: supabase.table("userbot_accounts").select("phone_number").execute())
        existing_data = getattr(existing, "data", None) or []
        existing_phones = {_normalize_phone(row.get("phone_number", "")) for row in existing_data}

        for phone in PHONE_NUMBERS_ENV_FALLBACK:
            phone = _normalize_phone(phone)
            if not phone or phone in existing_phones:
                continue
            try:
                await sb_execute(lambda: supabase.table("userbot_accounts").insert({
                    "phone_number": phone,
                    "status": "pending",
                    "two_fa_required": False,
                }).execute())
                print(f"✅ Yangi raqam qo'shildi: {phone}")
            except Exception as e:
                if "duplicate" not in str(e).lower():
                    print(f"⚠️ Raqam qo'shishda xato: {phone} - {e}")
    except Exception as e:
        print(f"⚠️ .env seed'da xato: {e}")


async def fetch_phone_numbers_from_db() -> list:
    if not supabase:
        return []
    try:
        res = await sb_execute(lambda: supabase.table("userbot_accounts").select("phone_number,status").execute())
        rows = getattr(res, "data", None) or []
        phones = []
        for row in rows:
            status = (row.get("status") or "").lower()
            phone = _normalize_phone(row.get("phone_number"))
            if not phone:
                continue
            if status in ["pending", "active", "connecting"]:
                phones.append(phone)
        return uniq_keep_order(phones)
    except Exception as e:
        print(f"⚠️ Bazadan raqamlarni olishda xato: {e}")
        return []


async def update_account_status(phone: str, status: str):
    if not supabase:
        return
    try:
        await sb_execute(lambda: supabase.table("userbot_accounts").update(
            {"status": status, "updated_at": "now()"}
        ).eq("phone_number", phone).execute())
        print(f"📊 Status yangilandi: {phone} -> {status}")
    except Exception as e:
        print(f"⚠️ Status yangilashda xato: {e}")


def create_message_handler(phone: str):
    async def handle_message(client: Client, message: Message):
        global last_cache_update, keywords_regex
        
        try:
            chat_id = message.chat.id
            group_name = getattr(message.chat, "title", None) or f"Chat {chat_id}"
            chat_type = getattr(message.chat, "type", None)
            chat_username = getattr(message.chat, "username", None)
            
            # Debug: BARCHA xabarlarni log qilish (keyword matchingdan avval)
            try:
                msg_text = message.text or ""
                msg_preview = msg_text[:50] if len(msg_text) > 50 else msg_text
            except Exception:
                msg_preview = "[Unicode error]"
            if DEBUG:
                if not chat_username:
                    print(f"🔒 [{phone}] Xabar keldi (yopiq): {group_name} | ID: {chat_id} | Matn: {msg_preview}...")
                else:
                    print(f"📨 [{phone}] Xabar keldi: @{chat_username} | Matn: {msg_preview}...")
            
            if normalize_chat_id(chat_id) in BLOKED_GROUP_IDS_NORM:
                if DEBUG:
                    print(f"🚫 [{phone}] Bloklangan guruh: {chat_id}")
                return

            now = time.time()
            if now - last_cache_update > CACHE_TTL:
                await refresh_keywords()

            cleaned_text, urls, raw_text = extract_text_and_urls(message)
        except Exception as e:
            print(f"❌ [{phone}] Xabar qayta ishlashda xato: {e}")
            import traceback
            traceback.print_exc()
            return

        if not keywords_regex:
            print(f"⚠️ [{phone}] keywords_regex yo'q - kalit so'zlar yuklanmagan!")
            return

        blob = (raw_text or cleaned_text or "")
        if not blob:
            if DEBUG and chat_id == -1002113606537:
                print(f"🔍 [DIAGNOSTIC] Хоразм: matn bo'sh!")
            return

        if DEBUG and len(blob) > 0:
            print(f"📝 [{phone}] Xabar tekshirilmoqda: {group_name} | Matn uzunligi: {len(blob)}")

        normalized_blob = normalize_text(blob)
        
        m = keywords_regex.search(blob)
        if not m:
            m = keywords_regex.search(normalized_blob)
        
        if not m:
            if DEBUG and not chat_username:
                print(f"❌ [{phone}] Kalit so'z topilmadi (yopiq guruh): {group_name}")
                print(f"   Asl matn: {blob[:80]}...")
                print(f"   Normalized: {normalized_blob[:80]}...")
                print(f"   Kalit so'zlar: {keywords_cache[:10]}...")
            return
        matched_keyword = m.group(0).lower()
        if DEBUG:
            print(f"🎯 [{phone}] Kalit so'z topildi: '{matched_keyword}' | Guruh: {group_name}")

        cache_key = (normalize_chat_id(chat_id), int(message.id))
        now = time.time()
        
        if DEBUG and chat_id == -1002113606537:
            print(f"🔍 [DIAGNOSTIC] Хоразм гурухи: cache_key={cache_key}, seen={cache_key in _seen_messages}")
        
        if cache_key in _seen_messages and now - _seen_messages[cache_key] < 60:
            if DEBUG:
                print(f"⏭️ [{phone}] Xabar allaqachon qayta ishlangan: {chat_id}/{message.id}")
            return
        _seen_messages[cache_key] = now
        if DEBUG:
            print(f"✅ [{phone}] Yangi xabar topildi: {chat_id}/{message.id}, kalit so'z: {matched_keyword}")

        # Cleanup old entries periodically
        if len(_seen_messages) > 5000:
            cutoff = now - 600  # 10 daqiqa
            to_del = [k for k, v in _seen_messages.items() if v < cutoff]
            for k in to_del:
                del _seen_messages[k]

        sender_html, sender_url, sender_plain, sender_info = build_sender_anchor(message)
        
        # Get user_id from message
        user_id = "N/A"
        if message.from_user:
            user_id = str(message.from_user.id)
        elif getattr(message, "sender_chat", None):
            user_id = str(message.sender_chat.id)
        
        message_link = get_message_link(message)
        group_link = get_chat_link(message)

        # cleaned_text is already HTML-safe (generated by extract_text_and_urls)
        # So we do NOT escape it again.
        safe_text = cleaned_text

        extra_links_text = ""
        if urls:
            show = urls[:3]
            extra_links_text = "\n\n" + "\n".join([f"🔗 {html.escape(u)}" for u in show])

        # Group ID for tracking private groups
        group_id_info = f"<code>{chat_id}</code>"

        # Build user action commands
        user_commands = f"💬 <code>/user {user_id}</code> - Malumot olish"
        if sender_url and sender_url.startswith("https://t.me/"):
            user_commands += f"\n👤 <a href=\"{html.escape(sender_url, quote=True)}\">Lichkaga o'tish</a>"
        else:
            # Username bo'lmagan foydalanuvchilar uchun user_id orqali lichkaga havola
            user_commands += f"\n👤 <a href=\"tg://user?id={user_id}\">Lichkaga o'tish</a>"

        forward_text = (
            f"🔔 <b>Yangi buyurtma</b>\n"
            f"📍 Guruh: <b>{html.escape(group_name)}</b> (ID: {group_id_info})\n"
            f"👤 Kimdan: {sender_html}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"ℹ️ {sender_info}\n\n"
            f"📋 <b>User buyruqlari:</b>\n{user_commands}\n\n"
            f"{safe_text}"
            f"{extra_links_text}\n\n"
            f"🔗 <a href=\"{html.escape(message_link, quote=True)}\">Xabar havolasi</a>"
        )

        asyncio.create_task(save_captured_message(
            cap_id=str(uuid.uuid4()),
            phone=phone,
            group_id=chat_id,
            group_name=group_name,
            message_id=message.id,
            sender_name=sender_plain,
            sender_link=sender_url or "",
            message_link=message_link,
            text=cleaned_text,
            urls=urls,
            keyword=matched_keyword
        ))

        asyncio.create_task(save_keyword_hit(matched_keyword, chat_id, group_name, phone, cleaned_text))

        item = ((normalize_chat_id(chat_id), int(message.id)), forward_text, group_link, message_link, urls, sender_url)

        # Xabar navbatga qo'shilishini log qilish
        print(f"📤 [{phone}] Xabar navbatga qo'shildi: {chat_id}/{message.id}")

        # Agar xabar shaxsiy chatdan kelsa, mijozga avtomatik javob yuborish
        if chat_type == "private" and message.from_user:
            try:
                reply_text = (
                    f"✅ Sizning xabaringiz qabul qilindi!\n"
                    f"📍 Operatorlar tez orada siz bilan bog'lanadi."
                )
                await client.send_message(
                    chat_id=chat_id,
                    text=reply_text
                )
                print(f"💬 [{phone}] Mijozga javob yuborildi: {chat_id}")
            except Exception as e:
                print(f"⚠️ [{phone}] Mijozga javob yuborishda xato: {e}")
        
        while True:
            try:
                send_queue.put_nowait(item)
                break
            except asyncio.QueueFull:
                print(f"⚠️ [{phone}] Navbat to'liq, kutish...")
                await asyncio.sleep(0.05)

    return handle_message


async def run_client(phone: str):
    print(f"\n📱 [{phone}] Ishga tushmoqda...")
    await update_account_status(phone, "connecting")

    session_base = session_base_for_phone(phone)

    client = Client(
        session_base,
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=phone,
        workers=32,
        sleep_threshold=30
    )

    client.on_message((filters.group | filters.channel) & filters.incoming)(create_message_handler(phone))

    try:
        await client.start()
        print(f"✅ [{phone}] Ulandi!")
        await update_account_status(phone, "active")

        await sync_all_groups(client, phone)
        print_statistics()

        async def periodic_sync():
            while True:
                await asyncio.sleep(SYNC_INTERVAL)
                try:
                    if client and client.is_connected:
                        await sync_all_groups(client, phone)
                        print_statistics()
                except Exception as e:
                    print(f"⚠️ [{phone}] Periodik sync xato: {e}")

        asyncio.create_task(periodic_sync())
        await asyncio.Event().wait()

    except Exception as e:
        msg = str(e)
        print(f"❌ [{phone}] Xato: {msg}")

        try:
            await client.stop()
        except Exception:
            pass

        if "AUTH_KEY_DUPLICATED" in msg:
            await update_account_status(phone, "duplicated_running_elsewhere")
            await notify_admin_once(
                f"dup_{phone}",
                "⚠️ AUTH_KEY_DUPLICATED\n"
                f"📱 Raqam: {phone}\n"
                "✅ Session o'chirilmadi.\n"
                "📌 Bu raqam boshqa joyda ishlayapti. O'sha joyni STOP qiling.\n"
                "🔁 Keyin qayta ishga tushiring."
            )
            return

        if "AUTH_KEY_UNREGISTERED" in msg:
            deleted = await safe_delete_session_files(session_base, tries=12)
            await update_account_status(phone, "relogin_required")
            await notify_admin_once(
                f"unreg_{phone}",
                "⚠️ AUTH_KEY_UNREGISTERED\n"
                f"📱 Raqam: {phone}\n"
                f"🧹 Session delete: {'✅' if deleted else '❌'}\n"
                "🔁 Qayta login kerak."
            )
            return

        await update_account_status(phone, "error")
        await notify_admin_once(f"err_{phone}", f"❌ Userbot error\n📱 {phone}\n🧾 {msg}")
        return


async def main():
    global ALL_PHONES, aiohttp_session

    print("🚀 UserBot Multi-Account ishga tushmoqda...")
    print(f"📁 BASE_DIR: {BASE_DIR}")
    print(f"📁 SESS_DIR: {SESS_DIR}")
    print(f"📁 CWD: {os.getcwd()}")
    print(f"🌐 PORTAL_BASE_URL: {PORTAL_BASE_URL}")

    if not init_supabase():
        print("❌ Supabase'ga ulanib bo'lmadi. Chiqish...")
        sys.exit(1)

    connector = aiohttp.TCPConnector(limit=300, ttl_dns_cache=300)
    aiohttp_session = aiohttp.ClientSession(connector=connector)

    for i in range(max(1, SEND_WORKERS)):
        asyncio.create_task(send_worker(i + 1))
    print(f"📤 Yuborish workerlari: {max(1, SEND_WORKERS)} ta | queue={QUEUE_MAX}")

    await load_groups_cache()
    await load_approved_users()
    await ensure_accounts_seeded_from_env()

    # Avval .env dan o'chiramiz, agar bo'sh bo'lsa bazadan
    phones = PHONE_NUMBERS_ENV_FALLBACK
    if not phones:
        phones = await fetch_phone_numbers_from_db()

    phones = uniq_keep_order(phones)
    ALL_PHONES = phones

    print(f"📱 Raqamlar soni: {len(phones)}")
    if not phones:
        print("❌ Bazada ham, .env fallback'da ham raqam yo'q!")
        sys.exit(1)

    await refresh_keywords()
    asyncio.create_task(periodic_keywords_refresh())

    # Bot polling ni ishga tushirish (background task)
    asyncio.create_task(bot_polling_loop())

    async def start_phone(p: str):
        if p in running_clients:
            return
        running_clients[p] = asyncio.create_task(run_client(p))

    print("\n🔄 Akkauntlar ishga tushirilmoqda...")
    for p in phones:
        await start_phone(p)

    await notify_admin_once("started", "✅ Userbot ishga tushdi.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 UserBot to'xtatildi")
    except Exception as e:
        print(f"❌ Kritik xato: {e}")
    finally:
        try:
            if aiohttp_session and not aiohttp_session.closed:
                asyncio.run(aiohttp_session.close())
        except Exception:
            pass

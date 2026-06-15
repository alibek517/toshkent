import os
import sys
import shutil
import logging
import asyncio
import re
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import User, Channel
from telethon.network import ConnectionTcpIntermediate
from telethon.errors import UserNotParticipantError

# Force standard streams to use UTF-8 to prevent encoding errors on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


# Telethon kutubxonasining batafsil va chalkash tarmoq loglarini o'chirib qo'yamiz (faqat jiddiy xatolarni ko'rsatadi)
logging.getLogger('telethon').setLevel(logging.ERROR)

# O'zimizning loglar uchun sodda va tushunarli format
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Userbot")

ENV_FILE = ".env"
SESSIONS_DIR = "sessions"

# Sessiya papkasini yaratish
os.makedirs(SESSIONS_DIR, exist_ok=True)

def migrate_old_sessions():
    """Eski sessiya fayllari loyiha papkasida bo'lsa, ularni 'sessions' papkasiga ko'chirish"""
    try:
        moved = False
        for file in os.listdir("."):
            if file.endswith(".session") and (file.startswith("session_") or file.startswith("bot_session")):
                old_path = file
                new_path = os.path.join(SESSIONS_DIR, file)
                if not os.path.exists(new_path):
                    shutil.move(old_path, new_path)
                    print(f"📁 [TIZIM] Sessiya fayli ko'chirildi: {old_path} -> {new_path}")
                    moved = True
                else:
                    os.remove(old_path)
        if moved:
            print("📁 [TIZIM] Barcha eski sessiyalar muvaffaqiyatli ko'chirildi!")
    except Exception as e:
        pass

migrate_old_sessions()

import sqlite3

# --- MA'LUMOTLAR BAZASI VA YORDAMCHI FUNKSIYALAR ---
DB_FILE = "bot_data.db"

def init_db():
    """SQLite ma'lumotlar bazasini va jadvallarni yaratish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Buyurtmalar jadvali (so'nggi buyurtmalarni saqlash va qidirish uchun)
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            msg_id INTEGER,
            text TEXT,
            from_city TEXT,
            to_city TEXT,
            phone TEXT,
            user_id INTEGER,
            username TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        # Haydovchilarning bildirishnoma yo'nalishlari
        c.execute('''CREATE TABLE IF NOT EXISTS driver_routes (
            user_id INTEGER,
            from_city TEXT,
            to_city TEXT,
            PRIMARY KEY (user_id, from_city, to_city)
        )''')
        conn.commit()
        conn.close()
        print("📁 [BAZA] Ma'lumotlar bazasi muvaffaqiyatli ishga tushirildi.")
    except Exception as e:
        print(f"❌ [BAZA XATO] Bazani yaratishda xato: {e}")

# Bazani ishga tushiramiz
init_db()

# Shaharlar ro'yxati va ularning variantlari (Lotin, Kirill, Rus tilida yozilishi)
CITIES = {
    'toshkent': ['toshkent', 'tashkent', 'toshket', 'tashket', 'тошкент', 'ташкент', 'toshk'],
    'urganch': ['urganch', 'urgench', 'urganç', 'урганч', 'urgan'],
    'xorazm': ['xorazm', 'xorazim', 'xarezm', 'хоразм', 'хоразим'],
    'nukus': ['nukus', 'nukis', 'нукус'],
    'buxoro': ['buxoro', 'buhoro', 'bukhoro', 'бухоро'],
    'samarqand': ['samarqand', 'samarkand', 'самарканд', 'samar'],
    'andijon': ['andijon', 'andijan', 'андижон', 'andi'],
    'fargona': ['fargona', 'farg\'ona', 'fergana', 'фаргона', 'vodiy'],
    'namangan': ['namangan', 'наманган', 'naman'],
    'qoqon': ['qoqon', 'qo\'qon', 'kokand', 'коканд'],
    'qarshi': ['qarshi', 'karshi', 'карши'],
    'termiz': ['termiz', 'termez', 'термиз'],
    'jizzax': ['jizzax', 'джизак', 'jizax'],
    'guliston': ['guliston', 'гулистан', 'guli'],
    'navoiy': ['navoiy', 'navoi', 'навои'],
    'beruniy': ['beruniy', 'бируни', 'беруний'],
    'turtkul': ['turtkul', 'to\'rtko\'l', 'туurtkul', 'туurtkol', 'турткул', 'тўрткўл'],
    'ellikqala': ['ellikqala', 'ellikala', 'элликкала', 'bo\'ston', 'biston'],
    'hazorasp': ['hazorasp', 'xazorasp', 'хазорасп'],
    'gurlan': ['gurlan', 'гурлан'],
    'xonqa': ['xonqa', 'хонка'],
    'shovot': ['shovot', 'шавот'],
    'mangit': ['mangit', 'мангит'],
    'qoshkopir': ['qoshkopir', 'qo\'shko\'pir', 'кошкупир']
}

# Shaharlar qisqa nomlari ro'yxati (tugmalar uchun oson ko'rinish)
CITY_LABELS = {
    'toshkent': 'Toshkent',
    'urganch': 'Urganch',
    'xorazm': 'Xorazm',
    'nukus': 'Nukus',
    'buxoro': 'Buxoro',
    'samarqand': 'Samarqand',
    'andijon': 'Andijon',
    'fargona': 'Farg\'ona',
    'namangan': 'Namangan',
    'qoqon': 'Qo\'qon',
    'qarshi': 'Qarshi',
    'termiz': 'Termiz',
    'jizzax': 'Jizzax',
    'guliston': 'Guliston',
    'navoiy': 'Navoiy'
}

def parse_route(text):
    """Matndan yo'nalishni (Qayerdan -> Qayerga) aniqlash.
       Qoidalar:
       1. Agar shahardan keyin 'dan'/'dan' kelsa - bu Qayerdan (from_city)
       2. Agar shahardan keyin 'ga'/'qa' kelsa - bu Qayerga (to_city)
       3. Agar shunchaki ikkita shahar nomi yozilgan bo'lsa, birinchisi Qayerdan, ikkinchisi Qayerga."""
    text_lower = text.lower()
    
    found_from = None
    found_to = None
    
    # 1. 'dan' va 'ga' qo'shimchalari bo'yicha qidirish
    for normalized_name, variants in CITIES.items():
        for var in variants:
            # Toshkentdan, Urganchdan, va hokazo
            if var + 'dan' in text_lower or var + 'dan' in text_lower or var + 'nan' in text_lower:
                found_from = normalized_name
            # Toshkentga, Urganchga, va hokazo
            if var + 'ga' in text_lower or var + 'qa' in text_lower or var + 'na' in text_lower:
                found_to = normalized_name

    # Agar qo'shimchalardan topilmagan bo'lsa, shunchaki so'z ketma-ketligi bo'yicha qidiramiz
    if not found_from or not found_to:
        words = text_lower.split()
        city_positions = []
        for word_idx, word in enumerate(words):
            # Tozalangan so'z
            clean_word = re.sub(r'[^\w\s]', '', word)
            for normalized_name, variants in CITIES.items():
                if any(var == clean_word for var in variants):
                    city_positions.append((word_idx, normalized_name))
                    break
        
        # Agar kamida 2 ta shahar topilgan bo'lsa va hali aniqlanmagan bo'lsa
        if len(city_positions) >= 2:
            if not found_from:
                found_from = city_positions[0][1]
            if not found_to:
                # Bir xil bo'lmasligini ta'minlaymiz
                for pos in city_positions[1:]:
                    if pos[1] != found_from:
                        found_to = pos[1]
                        break

    return found_from, found_to

def extract_phone(text):
    """Matndan telefon raqamini qidirib topish va formatlash"""
    # Oddiy regex o'zbek telefon formatlari uchun (masalan +998901234567, 90 123 45 67, 90-123-4567, 901234567)
    pattern = r'(?:\+?998)?\s?\(?\d{2}\)?\s?\d{3}\s?\d{2}\s?\d{2}'
    matches = re.findall(pattern, text)
    if matches:
        # Raqamni faqat raqamlardan iborat qilib tozalash
        raw_phone = re.sub(r'\D', '', matches[0])
        if len(raw_phone) == 9:
            return "+998" + raw_phone
        elif len(raw_phone) == 12:
            return "+" + raw_phone
        return matches[0]
    return ""

def store_order(chat_id, msg_id, text, from_city, to_city, phone, user_id, username):
    """Buyurtmani bazada saqlash"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO orders (chat_id, msg_id, text, from_city, to_city, phone, user_id, username)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (chat_id, msg_id, text, from_city, to_city, phone, user_id, username))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ [BAZA XATO] Buyurtmani saqlashda xato: {e}")

def get_active_orders(from_city, to_city, limit=10):
    """So'nggi faol (masalan oxirgi 12 soatdagi) buyurtmalarni yo'nalish bo'yicha qidirib olish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT text, timestamp, username, user_id FROM orders 
                     WHERE from_city = ? AND to_city = ? AND timestamp >= datetime('now', '-12 hour')
                     ORDER BY timestamp DESC LIMIT ?''', (from_city, to_city, limit))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ [BAZA XATO] Buyurtmalarni qidirishda xato: {e}")
        return []

def get_drivers_for_route(from_city, to_city):
    """Ushbu yo'nalish uchun bildirishnomani yoqib qo'ygan barcha haydovchilar ID sini olish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT user_id FROM driver_routes WHERE from_city = ? AND to_city = ?', (from_city, to_city))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"❌ [BAZA XATO] Haydovchilarni olishda xato: {e}")
        return []

def add_driver_route(user_id, from_city, to_city):
    """Haydovchiga yangi bildirishnoma yo'nalishini qo'shish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO driver_routes (user_id, from_city, to_city) VALUES (?, ?, ?)', 
                  (user_id, from_city, to_city))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ [BAZA XATO] Yo'nalish qo'shishda xato: {e}")
        return False

def clear_driver_routes(user_id):
    """Haydovchining barcha bildirishnomalarini o'chirish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM driver_routes WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ [BAZA XATO] Bildirishnomalarni o'chirishda xato: {e}")
        return False

def get_driver_routes(user_id):
    """Haydovchi obuna bo'lgan barcha yo'nalishlarni olish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT from_city, to_city FROM driver_routes WHERE user_id = ?', (user_id,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ [BAZA XATO] Obunalarni olishda xato: {e}")
        return []

async def is_user_driver(client, user_id):
    """Foydalanuvchi haydovchilar guruhida bor yoki yo'qligini tekshirish"""
    global target_group_entity
    target = target_group_entity or TARGET_GROUP_raw
    if not target:
        return False
    try:
        await client.get_permissions(target, user_id)
        return True
    except UserNotParticipantError:
        return False
    except Exception as e:
        logger.warning(f"Guruh a'zoligini tekshirishda xatolik: {e}")
        return False

def get_env_value(key):
    """Atrof-muhit o'zgaruvchisini yoki .env faylidagi qiymatni olish"""
    if os.environ.get(key):
        return os.environ.get(key)
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2 and parts[0].strip() == key:
                        return parts[1].strip()
    return ""

def save_env_values(config):
    """Qiymatlarni .env fayliga saqlash"""
    existing = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        existing[parts[0].strip()] = parts[1].strip()
    
    existing.update(config)
    
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# Telegram API sozlamalari (https://my.telegram.org saytidan olinadi)\n")
        f.write(f"API_ID={existing.get('API_ID', '')}\n")
        f.write(f"API_HASH={existing.get('API_HASH', '')}\n\n")
        f.write("# Telefon raqamlar ro'yxati (vergul bilan ajratilgan)\n")
        f.write(f"PHONE_NUMBERS={existing.get('PHONE_NUMBERS', '')}\n\n")
        f.write("# Xabarlar yuboriladigan guruh ID raqami yoki username'i\n")
        f.write(f"TARGET_GROUP={existing.get('TARGET_GROUP', '')}\n\n")
        f.write("# Telegram Bot Token (ixtiyoriy, xabarlarni userbot nomidan emas, bot nomidan yuborish uchun)\n")
        f.write(f"BOT_TOKEN={existing.get('BOT_TOKEN', '')}\n\n")
        f.write("# Qidiriladigan kalit so'zlar (vergul bilan ajratilgan)\n")
        f.write(f"KEYWORDS={existing.get('KEYWORDS', 'odam bor,moshina kerak,pochta bor,tayyor odam,kler,yuk bor,transport kerak,taxi bormikan,taxi kerak')}\n")

def setup_env_interactively():
    """Missing variables bo'lsa, ularni so'rash va .env ni yangilash"""
    config = {
        "API_ID": get_env_value("API_ID"),
        "API_HASH": get_env_value("API_HASH"),
        "PHONE_NUMBERS": get_env_value("PHONE_NUMBERS") or get_env_value("PHONE_NUMBER"),
        "TARGET_GROUP": get_env_value("TARGET_GROUP"),
        "BOT_TOKEN": get_env_value("BOT_TOKEN"),
        "KEYWORDS": get_env_value("KEYWORDS") or "odam bor,moshina kerak,pochta bor,tayyor odam,kler,yuk bor,transport kerak,taxi bormikan,taxi kerak"
    }
    
    dirty = False
    
    if not config["API_ID"] or not config["API_HASH"] or not config["PHONE_NUMBERS"] or not config["TARGET_GROUP"]:
        print("=" * 60)
        print(" TELEGRAM USERBOT MULTI-ACCOUNT SOZLAMALARI ")
        print("=" * 60)
        dirty = True
    
    try:
        if not config["API_ID"]:
            api_id = input("1. API ID (faqat raqamlar): ").strip()
            while not api_id.isdigit():
                api_id = input("Xato! API ID faqat raqam bo'lishi kerak. Qaytadan kiriting: ").strip()
            config["API_ID"] = api_id
            
        if not config["API_HASH"]:
            api_hash = input("2. API Hash (uzun harflar va raqamlar ketma-ketligi): ").strip()
            while not api_hash:
                api_hash = input("Xato! API Hash bo'sh bo'lishi mumkin emas. Qaytadan kiriting: ").strip()
            config["API_HASH"] = api_hash
            
        if not config["PHONE_NUMBERS"]:
            phone = input("3. Telefon raqamlari (vergul bilan ajratib yozing, masalan +998975002086,+998335800514): ").strip()
            while not phone:
                phone = input("Xato! Telefon raqamlarini kiriting: ").strip()
            config["PHONE_NUMBERS"] = phone
            
        if not config["TARGET_GROUP"]:
            target = input("4. Drivers guruhi (masalan @target_drivers_group yoki -100123456789): ").strip()
            while not target:
                target = input("Xato! Drivers guruhini kiriting: ").strip()
            config["TARGET_GROUP"] = target
            
        if dirty:
            save_env_values(config)
            print("-" * 60)
            print(".env fayli muvaffaqiyatli yangilandi!")
            print("=" * 60)
            
    except KeyboardInterrupt:
        print("\nSozlash bekor qilindi.")
        sys.exit(1)

# Sozlamalarni tekshirish va to'ldirish
setup_env_interactively()

load_dotenv()

try:
    API_ID = int(os.getenv("API_ID", "0"))
except ValueError:
    API_ID = 0
API_HASH = os.getenv("API_HASH", "")
PHONE_NUMBERS_raw = os.getenv("PHONE_NUMBERS", os.getenv("PHONE_NUMBER", ""))
TARGET_GROUP_raw = os.getenv("TARGET_GROUP", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
KEYWORDS_raw = os.getenv("KEYWORDS", "odam bor,moshina kerak,pochta bor,tayyor odam,kler,yuk bor,transport kerak,taxi bormikan,taxi kerak")
BLOCK_WORDS_raw = os.getenv("BLOCK_WORDS", "")
DRIVER_WORDS_raw = os.getenv("DRIVER_WORDS", "")

if not API_ID or not API_HASH or not PHONE_NUMBERS_raw:
    print("❌ XATOLIK: API_ID, API_HASH yoki PHONE_NUMBERS .env faylida ko'rsatilmagan!")
    sys.exit(1)

# Telefon raqamlarini ro'yxatga olish
PHONE_NUMBERS = [p.strip() for p in PHONE_NUMBERS_raw.split(",") if p.strip()]
# Kalit so'zlarni tozalab ro'yxatga olish (katta-kichik harflarsiz moslash uchun)
KEYWORDS = [kw.strip().lower() for kw in KEYWORDS_raw.split(",") if kw.strip()]
# Bloklangan so'zlarni ro'yxatga olish
BLOCK_WORDS = [bw.strip().lower() for bw in BLOCK_WORDS_raw.split(",") if bw.strip()]
# Bloklangan haydovchi so'zlarini ro'yxatga olish
DRIVER_WORDS = [dw.strip().lower() for dw in DRIVER_WORDS_raw.split(",") if dw.strip()]

# Regex patterns for ultra-fast C-compiled matching
keywords_pattern = re.compile('|'.join([re.escape(kw) for kw in KEYWORDS])) if KEYWORDS else None
block_words_pattern = re.compile('|'.join([re.escape(bw) for bw in BLOCK_WORDS])) if BLOCK_WORDS else None
driver_words_pattern = re.compile('|'.join([re.escape(dw) for dw in DRIVER_WORDS])) if DRIVER_WORDS else None

print(f"ℹ️ [SOZLAMALAR] Yuklangan telefonlar: {PHONE_NUMBERS}")
print(f"ℹ️ [SOZLAMALAR] Qidiriladigan so'zlar: {KEYWORDS}")
print(f"ℹ️ [SOZLAMALAR] Bloklangan so'zlar: {BLOCK_WORDS}")
print(f"ℹ️ [SOZLAMALAR] Bloklangan haydovchi so'zlari: {DRIVER_WORDS}")
print(f"ℹ️ [SOZLAMALAR] Nishon guruh ID/Username: {TARGET_GROUP_raw}")

# Faol mijozlar ro'yxati
clients = []
# Telegram Bot Client
bot_client = None

# Nishon guruh ID lari (cheksiz sikl/loop oldini olish uchun)
target_group_ids = set()

# TARGET_GROUP ID sini boshlang'ich tahlil qilish (tarmoqsiz tezkor ishlash uchun)
try:
    target_val = TARGET_GROUP_raw
    if target_val.startswith("-100") or target_val.isdigit() or (target_val.startswith("-") and target_val[1:].isdigit()):
        val_int = int(target_val)
        target_group_ids.add(val_int)
        str_val = str(val_int)
        if str_val.startswith("-100"):
            target_group_ids.add(int(str_val[4:]))
        else:
            target_group_ids.add(int(f"-100{str_val}"))
except Exception:
    pass

# Dublikatlarni oldini olish uchun kesh (in-memory deduplication)
processed_messages = set()
processed_list = []

def is_duplicate(chat_id, msg_id):
    """Xabar boshqa bir akkaunt orqali allaqachon qayta ishlanganligini tekshirish"""
    key = f"{chat_id}_{msg_id}"
    if key in processed_messages:
        return True
    processed_messages.add(key)
    processed_list.append(key)
    if len(processed_list) > 2000:
        oldest = processed_list.pop(0)
        processed_messages.discard(oldest)
    return False

# Nishon guruh ob'ekti (resolution kechikishining oldini olish uchun keshda saqlanadi)
target_group_entity = None

async def verify_target_group_access():
    """Nishon guruh haqiqiy ID sini aniqlash va ruxsatlarni tekshirish"""
    global target_group_ids, target_group_entity
    
    val = TARGET_GROUP_raw
    chat_id = val
    if val.startswith("-100") or val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
        try:
            val_int = int(val)
            target_group_ids.add(val_int)
            str_val = str(val_int)
            if str_val.startswith("-100"):
                target_group_ids.add(int(str_val[4:]))
            else:
                target_group_ids.add(int(f"-100{str_val}"))
            print(f"✅ [TIZIM] Nishon guruh ID raqami o'rnatildi: {val_int}")
        except Exception:
            pass

    has_access = False
    # Bot orqali aniqlash
    if bot_client:
        try:
            entity = await bot_client.get_entity(chat_id)
            target_group_entity = entity
            title = getattr(entity, 'title', 'Guruh')
            target_group_ids.add(entity.id)
            target_group_ids.add(int(str(entity.id).replace("-100", "")))
            print(f"🤖 [BOT API] Nishon guruh topildi va keshlandi: '{title}' (ID: {entity.id})")
            has_access = True
        except Exception:
            pass

    # Userbotlar orqali aniqlash
    for i, client in enumerate(clients):
        try:
            if not client.is_connected():
                continue
            entity = await client.get_entity(chat_id)
            if target_group_entity is None:
                target_group_entity = entity
            title = getattr(entity, 'title', 'Guruh')
            target_group_ids.add(entity.id)
            target_group_ids.add(int(str(entity.id).replace("-100", "")))
            print(f"👤 [AKKAUNT #{i+1}] Nishon guruh topildi va keshlandi: '{title}' (ID: {entity.id})")
            has_access = True
        except Exception:
            pass
            
    if not has_access:
        print("⚠️ [DIQQAT] Nishon guruh aniqlanmadi. Xabarlar faqat ID bo'yicha yuboriladi.")

async def send_to_target_group(message_text, reply_markup=None):
    """Xabarni drivers guruhiga yuborish (Bot yoki Userbotlar orqali)"""
    global target_group_entity
    
    val = TARGET_GROUP_raw
    chat_id = val
    if val.startswith("-100") or val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
        try:
            chat_id = int(val)
        except ValueError:
            pass

    # Keshdagi ob'ektdan foydalanamiz (agar mavjud bo'lsa, tezlikni oshirish uchun)
    to_entity = target_group_entity if target_group_entity is not None else chat_id

    # 1. Bot Token orqali yuborish
    if bot_client and bot_client.is_connected():
        try:
            # Avval tugmalari (markup) bilan birga yuboramiz
            await bot_client.send_message(to_entity, message_text, buttons=reply_markup, link_preview=False)
            print("🚀 [YUBORILDI] Xabar Telegram Bot orqali (tugmalari bilan) drivers guruhiga jo'natildi.")
            return True
        except Exception as e:
            if reply_markup:
                # Tugmalar bilan yuborish xato bersa (masalan callback tugma taqiqlangan bo'lsa), faqat matnni o'zini yuboramiz
                try:
                    await bot_client.send_message(to_entity, message_text, link_preview=False)
                    print(f"🚀 [YUBORILDI] Xabar Telegram Bot orqali (faqat matn, tugmalarsiz) jo'natildi. Tugma xatosi: {e}")
                    return True
                except Exception as e2:
                    print(f"⚠️ [BOT XATOLIGI] Bot Token orqali yuborishda xato: {e2}")
            else:
                print(f"⚠️ [BOT XATOLIGI] Bot Token orqali yuborishda xato: {e}")

    # 2. Akkauntlar orqali yuborish
    for i, client in enumerate(clients):
        if client.is_connected():
            try:
                await client.send_message(to_entity, message_text, buttons=reply_markup, link_preview=False)
                print(f"🚀 [YUBORILDI] Xabar Akkaunt #{i+1} ({PHONE_NUMBERS[i]}) orqali (tugmalari bilan) jo'natildi.")
                return True
            except Exception as e:
                if reply_markup:
                    try:
                        await client.send_message(to_entity, message_text, link_preview=False)
                        print(f"🚀 [YUBORILDI] Xabar Akkaunt #{i+1} ({PHONE_NUMBERS[i]}) orqali (faqat matn, tugmalarsiz) jo'natildi. Tugma xatosi: {e}")
                        return True
                    except Exception as e2:
                        print(f"⚠️ [USERBOT XATOLIGI] Akkaunt #{i+1} ({PHONE_NUMBERS[i]}) orqali yuborib bo'lmadi: {e2}")
                else:
                    print(f"⚠️ [USERBOT XATOLIGI] Akkaunt #{i+1} ({PHONE_NUMBERS[i]}) orqali yuborib bo'lmadi: {e}")
    
    print("❌ [XATO] Xabarni drivers guruhiga yuborish imkoni bo'lmadi! Guruh ruxsatlarini yoki ID to'g'riligini tekshiring.")
    return False

async def process_message(event):
    """Har bir xabarni tahlil qilish va yuborishni orqa fonda (background) bajaradi.
       Bu botning asosiy oqimi (event loop) bloklanmasligi va barcha xabarlarni parallel, tez o'qishini ta'minlaydi."""
    message_text = event.message.text
    if not message_text:
        return

    # Kelgan xabar maqsadli guruhdan bo'lsa, cheksiz sikl bo'lmasligi uchun qayta ishlamaymiz
    if event.chat_id in target_group_ids:
        return

    # Dublikat xabarlarni o'tkazib yuborish
    if is_duplicate(event.chat_id, event.message.id):
        return

    message_text_lower = message_text.lower()
    
    # Bloklangan so'zlarni tekshirish (agar birortasi topilsa, xabarni tashlab yuboramiz)
    if block_words_pattern and block_words_pattern.search(message_text_lower):
        return

    # Bloklangan haydovchi reklamalarini tekshirish (11-funksiya)
    if driver_words_pattern and driver_words_pattern.search(message_text_lower):
        return

    # Kalit so'z qidirish (regex bilan C-darajasida juda tez ishlaydi)
    matched_keyword = None
    if keywords_pattern:
        match = keywords_pattern.search(message_text_lower)
        if match:
            matched_keyword = match.group(0)

    # Agar kalit so'z topilmasa, bu yerda to'xtatamiz (tarmoq chaqiruvlari va printlarni chetlab o'tamiz)
    if not matched_keyword:
        return

    # Yo'nalishni aniqlaymiz (From -> To)
    from_city, to_city = parse_route(message_text)

    # Guruh va yuboruvchi ma'lumotlarini parallel (concurrently) yuklab, tarmoq kechikishini 50% ga kamaytiramiz
    chat_task = asyncio.create_task(event.get_chat()) if not event.chat else None
    sender_task = asyncio.create_task(event.get_sender()) if not event.sender else None

    # Xatolikka chidamli guruh ma'lumotlarini olish
    chat_title = "Guruh"
    chat_link = "Mavjud emas"
    msg_link = "Mavjud emas"
    
    try:
        chat = event.chat
        if chat_task:
            chat = await chat_task or event.chat
        if chat:
            chat_title = getattr(chat, 'title', 'Guruh')
            peer_str = str(event.chat_id)
            if peer_str.startswith("-100"):
                peer_str = peer_str[4:]
            
            if getattr(chat, 'username', None):
                chat_link = f"https://t.me/{chat.username}"
                msg_link = f"https://t.me/{chat.username}/{event.message.id}"
            else:
                chat_link = f"https://t.me/c/{peer_str}/999999999"
                msg_link = f"https://t.me/c/{peer_str}/{event.message.id}"
    except Exception:
        pass

    # Yuboruvchi ma'lumotlarini olish
    sender_name = "Noma'lum"
    username_str = ""
    user_mention = "Mavjud emas"
    phone_str = ""
    sender_id = None
    
    try:
        sender = event.sender
        if sender_task:
            sender = await sender_task or event.sender
        if sender:
            sender_id = sender.id
            if isinstance(sender, User):
                first_name = sender.first_name or ""
                last_name = sender.last_name or ""
                sender_name = f"{first_name} {last_name}".strip() or "Ismsiz"
                
                if sender.username:
                    username_str = f"@{sender.username}"
                    user_mention = f"[{sender_name}](tg://user?id={sender.id}) ({username_str})"
                else:
                    user_mention = f"[{sender_name}](tg://user?id={sender.id}) (Username yo'q)"
                    
                if sender.phone:
                    phone_str = f"+{sender.phone}"
            
            elif isinstance(sender, Channel):
                sender_name = sender.title or "Kanal/Guruh"
                if sender.username:
                    username_str = f"@{sender.username}"
                    user_mention = f"[{sender_name}](https://t.me/{sender.username})"
                else:
                    user_mention = f"{sender_name}"
    except Exception:
        pass

    # Telefon raqamini matndan qidiramiz
    phone_extracted = extract_phone(message_text)
    final_phone = phone_extracted or phone_str

    # Buyurtmani bazada saqlaymiz (direct search va push alertlar uchun)
    store_order(event.chat_id, event.message.id, message_text, from_city, to_city, final_phone, sender_id, username_str)

    print(f"🎯 [MOS KELDI] '{matched_keyword}' -> Guruh: '{chat_title}' | Yo'nalish: {from_city} -> {to_city} | Yuboruvchi: {sender_name}")

    # Xabarni chiroyli formatlash
    report_msg = (
        f"🚕 **YANGI BUYURTMA TOPILDI!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 **Mos kelgan so'z:** #{matched_keyword.replace(' ', '_')}\n"
        f"👥 **Guruh:** [{chat_title}]({chat_link})\n"
        f"👤 **Yuboruvchi:** {user_mention}\n"
    )
    
    if final_phone:
        report_msg += f"📞 **Telefon raqami:** {final_phone}\n"
        
    report_msg += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 **Xabar matni:**\n"
        f"\"{message_text}\"\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 **Original xabarni ko'rish:** [O'tish]({msg_link})"
    )

    # Lichkaga o'tish inline tugmasi (2-funksiya)
    inline_buttons = []
    if sender_id:
        if username_str:
            clean_user = username_str.replace("@", "")
            inline_buttons.append(Button.url("💬 Lichkaga yozish", f"https://t.me/{clean_user}"))
        else:
            inline_buttons.append(Button.url("💬 Lichkaga yozish", f"tg://user?id={sender_id}"))

    # Guruhga yuboramiz
    try:
        await send_to_target_group(report_msg, reply_markup=[inline_buttons] if inline_buttons else None)
    except Exception as ex:
        print(f"❌ [YUBORISHDA XATO] {ex}")

    # Obunachi haydovchilarga push-bildirishnoma yuborish (10-funksiya)
    if from_city and to_city and bot_client:
        try:
            driver_ids = get_drivers_for_route(from_city, to_city)
            if driver_ids:
                alert_msg = (
                    f"🔔 **SIZ KUZATAYOTGAN YO'NALISHDA BUYURTMA!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📍 Yo'nalish: #{from_city.upper()} ➡️ #{to_city.upper()}\n"
                    f"👤 Buyurtmachi: {user_mention}\n"
                    f"📝 Matn: \"{message_text}\"\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                )
                for d_id in driver_ids:
                    try:
                        await bot_client.send_message(d_id, alert_msg, buttons=[inline_buttons] if inline_buttons else None)
                        print(f"🔔 [PUSH] Haydovchi {d_id} ga bildirishnoma yuborildi.")
                    except Exception as alert_ex:
                        pass
        except Exception as e:
            print(f"❌ [PUSH XATO] Bildirishnoma yuborishda xato: {e}")

async def process_bot_private_message(event):
    """Foydalanuvchi botga shaxsiy xabar yuborganda buyurtma olish yoki menyuni ko'rsatish"""
    message_text = event.message.text
    if not message_text:
        return

    # A'zolikni tekshirish
    is_driver = await is_user_driver(event.client, event.sender_id)

    # Asosiy menyu tugmalari (faqat haydovchilar uchun)
    keyboard = [
        [Button.text("🔎 Buyurtma qidirish", resize=True), Button.text("🔔 Bildirishnoma sozlash")]
    ] if is_driver else Button.clear()

    # Agar haydovchi bo'lmagan foydalanuvchi haydovchi bo'limlariga kirmoqchi bo'lsa
    if message_text.strip() in ["🔎 Buyurtma qidirish", "🔔 Bildirishnoma sozlash"]:
        if not is_driver:
            await event.respond(
                "⚠️ **Ushbu bo'lim faqat haydovchilar uchun.**\n\n"
                "Haydovchilar guruhiga a'zo bo'lmagan foydalanuvchilar bu menyudan foydalana olmaydi.",
                buttons=Button.clear()
            )
            return

    # Agar foydalanuvchi /start yozgan bo'lsa yoki menyu tugmalaridan qaytsa
    if message_text.strip().lower() in ["/start", "back", "menyu"]:
        if is_driver:
            welcome_msg = (
                "🚕 **Assalomu alaykum! Toshkent-Xorazm taksi buyurtma botiga xush kelibsiz!**\n\n"
                "Siz bu yerda haydovchi sifatida buyurtmalarni qidirishingiz yoki yangi buyurtmalar haqida bildirishnoma sozlashishingiz mumkin.\n\n"
                "**Mijoz bo'lsangiz**, buyurtmangiz matnini shu yerga yozib yuboring (masalan: `Toshkentdan Urganchga 2 odam bor`)."
            )
        else:
            welcome_msg = (
                "🚕 **Assalomu alaykum! Toshkent-Xorazm taksi buyurtma botiga xush kelibsiz!**\n\n"
                "Buyurtmangiz matnini shu yerga yozib yuboring (masalan: `Toshkentdan Urganchga 2 odam bor`).\n"
                "Sizning buyurtmangiz haydovchilar guruhiga yuboriladi."
            )
        await event.respond(welcome_msg, buttons=keyboard)
        return

    # Buyurtma qidirish
    if message_text == "🔎 Buyurtma qidirish":
        buttons = [
            [Button.inline("Toshkent", b"search_from_toshkent"), Button.inline("Urganch", b"search_from_urganch"), Button.inline("Xorazm", b"search_from_xorazm")],
            [Button.inline("Nukus", b"search_from_nukus"), Button.inline("Buxoro", b"search_from_buxoro"), Button.inline("Samarqand", b"search_from_samarqand")],
            [Button.inline("Andijon", b"search_from_andijon"), Button.inline("Farg'ona", b"search_from_fargona"), Button.inline("Namangan", b"search_from_namangan")]
        ]
        await event.respond("📍 **Qayerdan** (qaysi shahardan ketasiz)? Tanlang:", buttons=buttons)
        return

    # Bildirishnomalarni sozlash
    if message_text == "🔔 Bildirishnoma sozlash":
        user_id = event.sender_id
        routes = get_driver_routes(user_id)
        if routes:
            msg = "🔔 **Siz obuna bo'lgan yo'nalishlar:**\n\n"
            for r in routes:
                msg += f"📍 {r[0].upper()} ➡️ {r[1].upper()}\n"
        else:
            msg = "🔔 Sizda hali faol bildirishnomalar yo'q. Yangi buyurtmalar haqida push-xabar olish uchun pastdagi tugmani bosing."
            
        buttons = [
            [Button.inline("➕ Yangi yo'nalish qo'shish", b"alert_add")],
            [Button.inline("❌ Barcha obunalarni o'chirish", b"alert_clear")]
        ]
        await event.respond(msg, buttons=buttons)
        return

    # Aks holda, bu taksi buyurtmasi deb hisoblanadi va drivers guruhiga yuboriladi
    sender = await event.get_sender()
    sender_name = "Noma'lum"
    user_mention = "Mavjud emas"
    sender_id = None
    username_str = ""
    
    if sender:
        sender_id = sender.id
        first_name = getattr(sender, 'first_name', '') or ''
        last_name = getattr(sender, 'last_name', '') or ''
        sender_name = f"{first_name} {last_name}".strip() or "Ismsiz"
        
        if getattr(sender, 'username', None):
            username_str = f"@{sender.username}"
            user_mention = f"[{sender_name}](tg://user?id={sender.id}) ({username_str})"
        else:
            user_mention = f"[{sender_name}](tg://user?id={sender.id}) (Username yo'q)"

    report_msg = (
        f"🚕 **BOT ORQALI YANGI BUYURTMA!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Buyurtmachi:** {user_mention}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 **Buyurtma matni:**\n"
        f"\"{message_text}\"\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )

    # Lichkaga o'tish tugmasi
    inline_buttons = []
    if sender_id:
        if username_str:
            clean_user = username_str.replace("@", "")
            inline_buttons.append(Button.url("💬 Lichkaga yozish", f"https://t.me/{clean_user}"))
        else:
            inline_buttons.append(Button.url("💬 Lichkaga yozish", f"tg://user?id={sender_id}"))

    # Guruhga yuboramiz
    sent = await send_to_target_group(report_msg, reply_markup=[inline_buttons] if inline_buttons else None)
    
    if sent:
        reply_msg = (
            "✅ **Sizning buyurtmangiz haydovchilar guruhiga muvaffaqiyatli yuborildi!**\n\n"
            "Tez orada haydovchilar siz bilan bog'lanishadi."
        )
    else:
        reply_msg = (
            "❌ **Xatolik yuz berdi.** Buyurtmangizni yuborib bo'lmadi.\n"
            "Iltimos, keyinroq qayta urinib ko'ring."
        )
        
    await event.respond(reply_msg, buttons=keyboard)

    # Buyurtmani bazada saqlash va push alertlar yuborish
    from_city, to_city = parse_route(message_text)
    phone_extracted = extract_phone(message_text)
    store_order(0, 0, message_text, from_city, to_city, phone_extracted, sender_id, username_str)

    if from_city and to_city and bot_client:
        try:
            driver_ids = get_drivers_for_route(from_city, to_city)
            if driver_ids:
                alert_msg = (
                    f"🔔 **SIZ KUZATAYOTGAN YO'NALISHDA BUYURTMA!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📍 Yo'nalish: #{from_city.upper()} ➡️ #{to_city.upper()}\n"
                    f"👤 Buyurtmachi: {user_mention}\n"
                    f"📝 Matn: \"{message_text}\"\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                )
                for d_id in driver_ids:
                    try:
                        await bot_client.send_message(d_id, alert_msg, buttons=[inline_buttons] if inline_buttons else None)
                    except Exception:
                        pass
        except Exception:
            pass

async def callback_handler(event):
    """Inline tugmalar bosilganda ishlash (Qidirish va Sozlash oynalari)"""
    user_id = event.sender_id
    
    # A'zolikni tekshirish (faqat haydovchilar callback'larni bossin)
    is_driver = await is_user_driver(event.client, user_id)
    if not is_driver:
        await event.answer("⚠️ Ushbu amal faqat guruh a'zolari (haydovchilar) uchun!", alert=True)
        return

    data = event.data.decode('utf-8')
    
    # --- BUYURTMA QIDIRISH (SEARCH) ---
    if data.startswith("search_from_"):
        from_city = data.replace("search_from_", "")
        buttons = [
            [Button.inline("Toshkent", f"search_to_{from_city}_toshkent".encode('utf-8')),
             Button.inline("Urganch", f"search_to_{from_city}_urganch".encode('utf-8')),
             Button.inline("Xorazm", f"search_to_{from_city}_xorazm".encode('utf-8'))],
            [Button.inline("Nukus", f"search_to_{from_city}_nukus".encode('utf-8')),
             Button.inline("Buxoro", f"search_to_{from_city}_buxoro".encode('utf-8')),
             Button.inline("Samarqand", f"search_to_{from_city}_samarqand".encode('utf-8'))],
            [Button.inline("Andijon", f"search_to_{from_city}_andijon".encode('utf-8')),
             Button.inline("Farg'ona", f"search_to_{from_city}_fargona".encode('utf-8')),
             Button.inline("Namangan", f"search_to_{from_city}_namangan".encode('utf-8'))]
        ]
        await event.edit(f"📍 Ketish: **{from_city.upper()}**\n\n🏁 **Qayerga** boradigan buyurtmalarni qidirmoqchisiz? Tanlang:", buttons=buttons)
        
    elif data.startswith("search_to_"):
        parts = data.replace("search_to_", "").split("_")
        from_city = parts[0]
        to_city = parts[1]
        
        # Bazadan buyurtmalarni olish
        orders = get_active_orders(from_city, to_city)
        
        result_msg = f"🔎 **Yo'nalish:** {from_city.upper()} ➡️ {to_city.upper()} bo'yicha so'nggi 12 soatdagi buyurtmalar:\n\n"
        if orders:
            for idx, order in enumerate(orders):
                text, timestamp, username, u_id = order
                time_str = timestamp.split()[1][:5] if ' ' in timestamp else timestamp
                user_link = f"@{username.replace('@','')}" if username else f"[Mijoz](tg://user?id={u_id})"
                result_msg += f"{idx+1}. 🕒 **{time_str}** | {user_link}\nMatn: \"{text}\"\n\n"
        else:
            result_msg += "❌ Hozircha faol buyurtmalar topilmadi."
            
        await event.edit(result_msg)

    # --- BILDIRISHNOMALAR (ALERTS) ---
    elif data == "alert_add":
        buttons = [
            [Button.inline("Toshkent", b"alert_from_toshkent"), Button.inline("Urganch", b"alert_from_urganch"), Button.inline("Xorazm", b"alert_from_xorazm")],
            [Button.inline("Nukus", b"alert_from_nukus"), Button.inline("Buxoro", b"alert_from_buxoro"), Button.inline("Samarqand", b"alert_from_samarqand")],
            [Button.inline("Andijon", b"alert_from_andijon"), Button.inline("Farg'ona", b"alert_from_fargona"), Button.inline("Namangan", b"alert_from_namangan")]
        ]
        await event.edit("🔔 **Bildirishnoma qo'shish**\n\n📍 **Qayerdan** buyurtma tushganda xabar beraylik? Tanlang:", buttons=buttons)
        
    elif data.startswith("alert_from_"):
        from_city = data.replace("alert_from_", "")
        buttons = [
            [Button.inline("Toshkent", f"alert_to_{from_city}_toshkent".encode('utf-8')),
             Button.inline("Urganch", f"alert_to_{from_city}_urganch".encode('utf-8')),
             Button.inline("Xorazm", f"alert_to_{from_city}_xorazm".encode('utf-8'))],
            [Button.inline("Nukus", f"alert_to_{from_city}_nukus".encode('utf-8')),
             Button.inline("Buxoro", f"alert_to_{from_city}_buxoro".encode('utf-8')),
             Button.inline("Samarqand", f"alert_to_{from_city}_samarqand".encode('utf-8'))],
            [Button.inline("Andijon", f"alert_to_{from_city}_andijon".encode('utf-8')),
             Button.inline("Farg'ona", f"alert_to_{from_city}_fargona".encode('utf-8')),
             Button.inline("Namangan", f"alert_to_{from_city}_namangan".encode('utf-8'))]
        ]
        await event.edit(f"🔔 Ketish: **{from_city.upper()}**\n\n🏁 **Qayerga** buyurtma bo'lganda xabar yuboraylik? Tanlang:", buttons=buttons)
        
    elif data.startswith("alert_to_"):
        parts = data.replace("alert_to_", "").split("_")
        from_city = parts[0]
        to_city = parts[1]
        
        success = add_driver_route(user_id, from_city, to_city)
        if success:
            await event.edit(f"✅ **Muvaffaqiyatli obuna bo'lindingiz!**\n\nEndi **{from_city.upper()} ➡️ {to_city.upper()}** yo'nalishi bo'yicha yangi buyurtma tushganda sizga push-xabar keladi.")
        else:
            await event.edit("❌ Xatolik yuz berdi. Iltimos keyinroq qayta urinib ko'ring.")
            
    elif data == "alert_clear":
        success = clear_driver_routes(user_id)
        if success:
            await event.edit("❌ **Barcha obunalaringiz muvaffaqiyatli o'chirildi.**")
        else:
            await event.edit("❌ Xatolik yuz berdi.")

async def message_handler(event):
    # Agar xabar shaxsiy chatdan (lichkadan) kelgan bo'lsa
    if event.is_private:
        # Faqat botga kelgan shaxsiy xabarlarni qayta ishlaymiz (userbot lichkalarini o'qimaymiz)
        if bot_client and event.client == bot_client:
            asyncio.create_task(process_bot_private_message(event))
        return

    # Guruhlar va kanallardagi xabarlarni qayta ishlash
    if bot_client and event.client == bot_client:
        # Bot guruhlarda xabarlarni o'qib kalit so'z qidirmaydi (buni userbotlar bajaradi)
        return
        
    # Xabarni qayta ishlashni orqa fonda ishga tushiramiz (background task)
    asyncio.create_task(process_message(event))

async def main():
    global clients, bot_client
    
    print("=" * 60)
    print(" TIZIM ISHGA TUSHMOQDA... ")
    print("=" * 60)
    
    # 1. Telegram Bot Token faollashtirish
    if BOT_TOKEN:
        print("🤖 [BOT] Telegram Bot API ga ulanish...")
        session_path = os.path.join(SESSIONS_DIR, "bot_session")
        bot_client = TelegramClient(
            session_path, 
            API_ID, 
            API_HASH,
            connection=ConnectionTcpIntermediate, # Yuqori tezlikda ulanish uchun engil protokol
            connection_retries=None,               # Cheksiz qayta ulanish urinishi
            retry_delay=5,                          # Qayta ulanish oralig'i (soniya)
            auto_reconnect=True,
            flood_sleep_threshold=24 * 3600         # Telegram cheklovi bo'lsa avtomat kutish
        )
        try:
            await bot_client.start(bot_token=BOT_TOKEN)
            bot_client.add_event_handler(message_handler, events.NewMessage)
            bot_client.add_event_handler(callback_handler, events.CallbackQuery)
            print("🤖 [BOT] Telegram Bot muvaffaqiyatli ishga tushdi va ulandi!")
        except Exception as e:
            print(f"❌ [BOT XATO] Bot Token orqali ulanishda xato: {e}")

    # 2. Akkauntlarni (Userbot) ulash
    print("👤 [USERBOT] Akkauntlarni tizimga ulash boshlanmoqda...")
    for idx, phone in enumerate(PHONE_NUMBERS):
        print(f"👤 [USERBOT] Akkaunt #{idx+1} ({phone}) ulanmoqda...")
        session_name = f"session_{phone.replace('+', '').replace(' ', '').strip()}"
        session_path = os.path.join(SESSIONS_DIR, session_name)
        
        client = TelegramClient(
            session_path, 
            API_ID, 
            API_HASH,
            connection=ConnectionTcpIntermediate, # Eng tezkor TCP protokoli
            connection_retries=None,               # Cheksiz qayta ulanish
            retry_delay=5,                          # Tarmoq o'chib yonsa har 5 soniyada ulanishga urinadi
            auto_reconnect=True,
            flood_sleep_threshold=24 * 3600
        )
        
        try:
            await client.start(phone=phone)
            print(f"👤 [USERBOT] Akkaunt #{idx+1} ({phone}) muvaffaqiyatli ulandi!")
            client.add_event_handler(message_handler, events.NewMessage)
            clients.append(client)
        except Exception as e:
            print(f"❌ [USERBOT XATO] Akkaunt ({phone}) ulanishida xatolik: {e}")
        
    if not clients:
        print("❌ XATOLIK: Birorta ham akkaunt ulanmadi. Ish tugatildi.")
        sys.exit(1)
        
    print("✅ [TIZIM] Barcha faol akkauntlar muvaffaqiyatli ulangan!")
    
    # Guruhga ulanish ruxsatlarini tekshiramiz (bu fon rejimida ishlaydi, ulanishni to'xtatib qo'ymaydi)
    asyncio.create_task(verify_target_group_access())
    
    # Akkauntlardagi guruhlar sonini chiqarish (fon rejimida, tezkor ishga tushish uchun)
    async def log_groups():
        for i, client in enumerate(clients):
            try:
                dialogs = await client.get_dialogs()
                groups_count = sum(1 for d in dialogs if d.is_group)
                print(f"📊 [STASTISTIKA] Akkaunt #{i+1} ({PHONE_NUMBERS[i]}): {groups_count} ta guruh kuzatilmoqda.")
            except Exception:
                pass
    asyncio.create_task(log_groups())
    
    print("\n🚀 [TIZIM] Tizim to'liq ishga tushdi va xabarlarni kuzatmoqda!")
    print("ℹ️ Tarmoq uzilsa, bot o'zi avtomatik ravishda qayta ulanadi (Ctrl+C bilan to'xtatishingiz mumkin).\n")
    
    # Barcha mijozlarning ulanishini ushlab turish
    run_tasks = [client.run_until_disconnected() for client in clients]
    if bot_client:
        run_tasks.append(bot_client.run_until_disconnected())
        
    await asyncio.gather(*run_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 [TIZIM] Botlar faoliyati foydalanuvchi tomonidan to'xtatildi.")
    except Exception as e:
        print(f"❌ [TIZIM XATO] Kutilmagan xato yuz berdi: {e}")

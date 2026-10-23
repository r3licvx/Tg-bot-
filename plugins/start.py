# ==============================================================================
# 🎬 TGFLIX FILE SERVING ENGINE (GD-HBX MINIMAL ARCHITECTURE)
# ⚡ Clean Monospace Box | Dynamic Status Indicator | Robust Delete Fix
# ==============================================================================

import asyncio
import json
import os
import random
import sys
import time
from urllib.parse import quote_plus, urlparse

import aiohttp
from pyrogram import enums, filters
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    FloodWait,
    MessageNotModified,
    PeerIdInvalid,
)
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

try:
    from TechVJ.bot import TechVJBot
    from TechVJ.util.file_properties import get_hash, get_name
except Exception:
    from bot import TechVJBot
    from util.file_properties import get_name, get_hash

from info import HTTP_URL, HTTPS_URL, LOG_CHANNEL

# ==============================================================================
# 👑 CONFIGURATION & METRICS
# ==============================================================================

ADMIN_IDS = [7890966750, 7475029864]
ADMIN_CONTACT_ID = 7890966750

BOT_RELEASE = "v1.6.5-beta"
ENGINE_NAME = "HyperUpload Engine"

START_TIME = time.time()

WAITING_BROADCAST = set()
WAITING_URL_UPLOAD = set()

DB_FILE = "database.json"
SUPPORTED_LANGUAGES = ["en", "hi"]

# ==============================================================================
# 💾 DATABASE OPERATIONS
# ==============================================================================

def load_db():
    default = {
        "users": {},
        "banned": [],
        "files": {}
    }
    if not os.path.exists(DB_FILE):
        return default
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return default


def save_db(data):
    tmp_file = DB_FILE + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_file, DB_FILE)
    except Exception as e:
        print(f"Database Save Error: {e}")


db_data = load_db()

KNOWN_USERS = db_data.get("users", {})
BANNED_USERS = set(int(x) for x in db_data.get("banned", []))
FILE_CACHE = db_data.get("files", {})


def sync_data():
    save_db({
        "users": KNOWN_USERS,
        "banned": list(BANNED_USERS),
        "files": FILE_CACHE
    })


# ==============================================================================
# 🛠 UTILITIES & INDICATORS
# ==============================================================================

def get_readable_uptime() -> str:
    uptime_sec = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def get_status_indicator() -> str:
    uptime_sec = int(time.time() - START_TIME)
    if uptime_sec < 86400 * 7:
        return "🟢 Active"
    return "🟡 Stable"


def trim_filename(name: str, max_len: int = 24) -> str:
    if not name or len(name) <= max_len:
        return name or "Media_File"
    if "." in name:
        base, ext = name.rsplit(".", 1)
        ext = "." + ext
    else:
        base, ext = name, ""
    allowed_base = max_len - len(ext) - 3
    if allowed_base <= 4:
        return name[:max_len - 3] + "..."
    half = allowed_base // 2
    return f"{base[:half]}...{base[-half:]}{ext}"


def humanbytes(size):
    if not size:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_authorized(m: Message) -> bool:
    if m.from_user and m.from_user.id in ADMIN_IDS:
        return True
    return bool(m.chat and (m.chat.id == LOG_CHANNEL or str(m.chat.id) == str(LOG_CHANNEL)))


def safe_extract_name(message):
    try:
        raw_name = get_name(message)
        if raw_name:
            return str(raw_name)
    except Exception:
        pass
    media = (
        message.video or message.document or message.audio or message.voice or
        (message.photo[-1] if message.photo else None)
    )
    if media:
        if getattr(media, "file_name", None):
            return str(media.file_name)
        return f"file_{media.file_unique_id}"
    return "Media_File"


def safe_extract_hash(message):
    try:
        raw_hash = get_hash(message)
        if raw_hash:
            return str(raw_hash)
    except Exception:
        pass
    media = (
        message.video or message.document or message.audio or message.voice or
        (message.photo[-1] if message.photo else None)
    )
    if media:
        return str(getattr(media, "file_unique_id", "stream"))
    return "stream"


def safe_quote(val):
    if val is None:
        return ""
    if isinstance(val, bytes):
        return quote_plus(val.decode("utf-8", errors="ignore"))
    return quote_plus(str(val))


def remove_file_from_cache_by_msg_id(msg_id):
    keys = [k for k, v in FILE_CACHE.items() if v.get("msg_id") == msg_id]
    for k in keys:
        del FILE_CACHE[k]
    if keys:
        sync_data()


# ==============================================================================
# 🌐 LANGUAGE PROFILE MANAGEMENT
# ==============================================================================

def get_user_language(user_id: int):
    data = KNOWN_USERS.get(str(user_id), {})
    lang = data.get("language")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def ensure_user_record(user):
    if not user:
        return False
    uid = str(user.id)
    if uid not in KNOWN_USERS:
        KNOWN_USERS[uid] = {
            "name": user.first_name or "User",
            "username": user.username or "None",
            "id": user.id,
            "language": None
        }
        sync_data()
        return True

    data = KNOWN_USERS[uid]
    changed = False
    for k, v in [
        ("name", user.first_name or "User"),
        ("username", user.username or "None"),
        ("id", user.id)
    ]:
        if data.get(k) != v:
            data[k] = v
            changed = True
    if "language" not in data:
        data["language"] = None
        changed = True
    if changed:
        sync_data()
    return False


# ==============================================================================
# 🎨 CLEAN BOX UI (STRUCTURED WHITESPACE, ZERO CLUTTER)
# ==============================================================================

def build_dashboard_text(first_name: str, lang: str = "en") -> str:
    uptime_str = get_readable_uptime()
    status_tag = get_status_indicator()

    if lang == "hi":
        return (
            "☰ <b>TgFlix File Serving Bot (GD-HBX)</b>\n\n"
            "⇒ <b>System Status :</b>\n"
            f"├ Status  : <code>{status_tag}</code>\n"
            f"├ Uptime  : <code>{uptime_str}</code>\n"
            f"├ Release : <code>{BOT_RELEASE}</code>\n"
            f"└ Engine  : <code>{ENGINE_NAME}</code>\n\n"
            "⇒ <b>Description :</b>\n"
            f"├ नमस्ते {first_name}, फाइल स्ट्रीमिंग सर्विस तैयार है।\n"
            "└ कोई भी मीडिया फ़ाइल या डायरेक्ट लिंक भेजें।"
        )

    return (
        "☰ <b>TgFlix File Serving Bot (GD-HBX)</b>\n\n"
        "⇒ <b>System Status :</b>\n"
        f"├ Status  : <code>{status_tag}</code>\n"
        f"├ Uptime  : <code>{uptime_str}</code>\n"
        f"├ Release : <code>{BOT_RELEASE}</code>\n"
        f"└ Engine  : <code>{ENGINE_NAME}</code>\n\n"
        "⇒ <b>Description :</b>\n"
        f"├ Hello {first_name}, autonomous file delivery is online.\n"
        "└ Drop any file or valid link to generate direct streams."
    )


def get_start_markup(lang: str = "en"):
    refresh_text = "↻ Refresh" if lang == "en" else "↻ रीफ्रेश"
    settings_text = "Settings" if lang == "en" else "सेटिंग्स"
    support_text = "Support" if lang == "en" else "सहायता"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(refresh_text, callback_data="refresh_status")
        ],
        [
            InlineKeyboardButton(settings_text, callback_data="open_settings"),
            InlineKeyboardButton(support_text, url=f"tg://user?id={ADMIN_CONTACT_ID}")
        ]
    ])


def get_language_selector_text():
    return (
        "☰ <b>TgFlix Configuration</b>\n\n"
        "⇒ <b>Language / भाषा :</b>\n"
        "├ Select your interface language to continue.\n"
        "└ आगे बढ़ने के लिए अपनी भाषा का चयन करें।"
    )


def get_language_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="lang_hi"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
        ]
    ])


def build_media_card(file_name, file_size, file_ext, http_link, https_link, lang="en"):
    clean_name = trim_filename(file_name, 26)
    return (
        "☰ <b>TgFlix Delivery Ready</b>\n\n"
        "⇒ <b>Metadata :</b>\n"
        f"├ File   : <code>{clean_name}</code>\n"
        f"├ Size   : <code>{file_size}</code>\n"
        f"└ Format : <code>{file_ext}</code>\n\n"
        "⇒ <b>Direct Endpoints :</b>\n"
        f"├ <a href=\"{http_link}\">Fast Stream (Standard)</a>\n"
        f"└ <a href=\"{https_link}\">Secure HTTPS (Encrypted)</a>"
    )


def get_user_buttons(stream_url, download_url, delete_msg_id=None, lang="en"):
    stream_title = "Stream" if lang == "en" else "स्ट्रीम"
    download_title = "Download" if lang == "en" else "डाउनलोड"
    support_title = "Support" if lang == "en" else "सहायता"

    buttons = [
        [
            InlineKeyboardButton(stream_title, url=stream_url),
            InlineKeyboardButton(download_title, url=download_url)
        ],
        [
            InlineKeyboardButton(support_title, url=f"tg://user?id={ADMIN_CONTACT_ID}")
        ]
    ]
    if delete_msg_id:
        del_label = "Remove File" if lang == "en" else "फ़ाइल हटाएं"
        buttons.append([
            InlineKeyboardButton(del_label, callback_data=f"del_{delete_msg_id}")
        ])
    return InlineKeyboardMarkup(buttons)


def build_banned_card(lang="en"):
    if lang == "hi":
        text = (
            "☰ <b>TgFlix Security Protection</b>\n\n"
            "⇒ <b>Access Status :</b>\n"
            "├ स्थिति : <code>प्रतिबंधित</code>\n"
            "└ आपका एक्सेस निलंबित कर दिया गया है।"
        )
    else:
        text = (
            "☰ <b>TgFlix Security Protection</b>\n\n"
            "⇒ <b>Access Status :</b>\n"
            "├ Status : <code>Suspended</code>\n"
            "└ Your account access is restricted on this engine."
        )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("Support", url=f"tg://user?id={ADMIN_CONTACT_ID}")
    ]])
    return text, markup


def get_admin_action_markup(user_id: int, file_msg_id=None):
    row = []
    if user_id in BANNED_USERS:
        row.append(InlineKeyboardButton("Unban", callback_data=f"unban_{user_id}"))
    else:
        row.append(InlineKeyboardButton("Ban", callback_data=f"ban_{user_id}"))
    row.append(InlineKeyboardButton("Info", callback_data=f"info_{user_id}"))

    buttons = [row]
    if file_msg_id:
        buttons.append([InlineKeyboardButton("Delete Media", callback_data=f"del_{file_msg_id}")])
    return InlineKeyboardMarkup(buttons)


def build_progress_card(progress: int, status_text: str, lang: str = "en") -> str:
    bar_length = 8
    filled = int(progress / (100 / bar_length))
    bar = "■" * filled + "□" * (bar_length - filled)
    return (
        "☰ <b>TgFlix Pipeline</b>\n\n"
        "⇒ <b>Task Status :</b>\n"
        f"├ Progress : <code>[{bar}] {progress}%</code>\n"
        f"└ State    : <code>{status_text}</code>"
    )


# ==============================================================================
# 📤 FILE UPLOAD ENGINE WITH RETRY
# ==============================================================================

async def upload_file_with_retry(fid, retries=5):
    for attempt in range(retries):
        try:
            result = await TechVJBot.send_cached_media(LOG_CHANNEL, fid)
            if result:
                return result
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except (ChannelPrivate, ChatAdminRequired, PeerIdInvalid) as err:
            raise Exception(f"LOG_CHANNEL issue ({err})")
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2)
    raise Exception("Upload failed after retries")


# ==============================================================================
# 🚀 /START COMMAND
# ==============================================================================

@TechVJBot.on_message(filters.command("start") & filters.private)
async def start(client, m: Message):
    user = m.from_user
    if user.id in BANNED_USERS:
        msg, btn = build_banned_card(get_user_language(user.id))
        await m.reply_text(msg, reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    is_new = ensure_user_record(user)
    data = KNOWN_USERS.get(str(user.id), {})
    lang = data.get("language")

    if is_new or lang not in SUPPORTED_LANGUAGES:
        if is_new:
            try:
                markup = get_admin_action_markup(user.id)
                admin_notice = (
                    "☰ <b>New User Registration</b>\n\n"
                    "⇒ <b>User Meta :</b>\n"
                    f"├ Name : {user.mention}\n"
                    f"├ ID   : <code>{user.id}</code>\n"
                    f"└ Tag  : @{user.username or 'None'}"
                )
                await client.send_message(
                    LOG_CHANNEL,
                    admin_notice,
                    reply_markup=markup,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception as e:
                print(f"Log Error: {e}")

        await m.reply_text(
            get_language_selector_text(),
            reply_markup=get_language_markup(),
            quote=True,
            parse_mode=enums.ParseMode.HTML
        )
        return

    dashboard_text = build_dashboard_text(user.first_name, lang=lang)
    await m.reply_text(
        dashboard_text,
        reply_markup=get_start_markup(lang),
        quote=True,
        parse_mode=enums.ParseMode.HTML
    )


# ==============================================================================
# 🌐 /SETTINGS COMMAND
# ==============================================================================

@TechVJBot.on_message(filters.command("settings") & filters.private)
async def settings_command(client, m: Message):
    user = m.from_user
    if user.id in BANNED_USERS:
        msg, btn = build_banned_card(get_user_language(user.id))
        await m.reply_text(msg, reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    ensure_user_record(user)
    await m.reply_text(
        get_language_selector_text(),
        reply_markup=get_language_markup(),
        quote=True,
        parse_mode=enums.ParseMode.HTML
    )


# ==============================================================================
# 🌐 /UPLOAD_URL COMMAND & PROCESSOR
# ==============================================================================

@TechVJBot.on_message(filters.command("upload_url") & filters.private)
async def upload_url_command(client, m: Message):
    user = m.from_user
    if user.id in BANNED_USERS:
        msg, btn = build_banned_card(get_user_language(user.id))
        await m.reply_text(msg, reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    ensure_user_record(user)
    WAITING_URL_UPLOAD.add(user.id)
    lang = get_user_language(user.id)

    if lang == "hi":
        text = (
            "☰ <b>TgFlix URL Ingestion</b>\n\n"
            "⇒ <b>Input Required :</b>\n"
            "├ अपनी डायरेक्ट फ़ाइल का HTTP/HTTPS लिंक नीचे भेजें।\n"
            "└ सिस्टम तुरंत स्ट्रीम तैयार करेगा।"
        )
    else:
        text = (
            "☰ <b>TgFlix URL Ingestion</b>\n\n"
            "⇒ <b>Input Required :</b>\n"
            "├ Send any valid HTTP/HTTPS media URL below.\n"
            "└ Engine will process direct streaming routes."
        )

    await m.reply_text(text, quote=True, parse_mode=enums.ParseMode.HTML)


async def process_url_ingestion(client, m: Message, url_text: str):
    user_id = m.from_user.id
    lang = get_user_language(user_id)

    if user_id in BANNED_USERS:
        msg, btn = build_banned_card(lang)
        await m.reply_text(msg, reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    url_hash_id = safe_quote(url_text)
    if url_hash_id in FILE_CACHE:
        cached = FILE_CACHE[url_hash_id]
        try:
            chk = await client.get_messages(LOG_CHANNEL, cached["msg_id"])
            if chk and not chk.empty:
                http_link = f"{HTTP_URL}url?src={url_hash_id}"
                https_link = f"{HTTPS_URL}url?src={url_hash_id}"
                direct_dl_link = f"{HTTPS_URL}url?src={url_hash_id}&download=1"
                markup = get_user_buttons(https_link, direct_dl_link, delete_msg_id=cached["msg_id"], lang=lang)
                await m.reply_text(
                    build_media_card(cached.get("name", "Direct_URL_File"), cached["size_str"], cached["ext"], http_link, https_link, lang),
                    disable_web_page_preview=True,
                    reply_markup=markup,
                    quote=True,
                    parse_mode=enums.ParseMode.HTML
                )
                return
            del FILE_CACHE[url_hash_id]
            sync_data()
        except Exception:
            FILE_CACHE.pop(url_hash_id, None)
            sync_data()

    parsed = urlparse(url_text)
    if not parsed.scheme or not parsed.netloc:
        err_text = (
            "☰ <b>TgFlix Error</b>\n\n"
            "⇒ <b>Verification Failed :</b>\n"
            "├ Invalid URL format.\n"
            "└ Please provide a direct HTTP or HTTPS address."
        )
        await m.reply_text(err_text, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    status_msg = await m.reply_text(
        build_progress_card(25, "Inspecting URL...", lang),
        quote=True,
        parse_mode=enums.ParseMode.HTML
    )
    await asyncio.sleep(0.3)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_text, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status not in [200, 206]:
                    await status_msg.edit_text(
                        f"☰ <b>TgFlix Error</b>\n\n⇒ <b>Connection Failed :</b>\n├ Status : <code>{resp.status}</code>\n└ Link unreachable.",
                        parse_mode=enums.ParseMode.HTML
                    )
                    return
                content_len = int(resp.headers.get("Content-Length", 0))
                clean_path = url_text.split("?")[0]
                url_file_name = clean_path.split("/")[-1] or "Direct_Stream"
                ext = clean_path.split(".")[-1].upper() if "." in clean_path else "MP4"
                if len(ext) > 5 or not ext.isalnum():
                    ext = "MP4"
                size_str = humanbytes(content_len)
                http_link = f"{HTTP_URL}url?src={url_hash_id}"
                https_link = f"{HTTPS_URL}url?src={url_hash_id}"
                direct_dl_link = f"{HTTPS_URL}url?src={url_hash_id}&download=1"

                admin_log_caption = (
                    "☰ <b>GDFlix Media Record (GD-HBX)</b>\n\n"
                    "⇒ <b>Upload Details :</b>\n"
                    f"├ User : {m.from_user.mention}\n"
                    f"├ ID   : <code>{user_id}</code>\n"
                    f"├ File : <code>{trim_filename(url_file_name, 26)}</code>\n"
                    f"├ Size : <code>{size_str}</code> (.{ext})\n"
                    "└ Type : Direct URL Ingest\n\n"
                    f"<a href=\"{http_link}\">HTTP</a> | <a href=\"{https_link}\">HTTPS</a>"
                )
                log_msg_id = 0
                try:
                    log_btn = get_admin_action_markup(user_id, "del_url")
                    log = await client.send_message(
                        LOG_CHANNEL,
                        admin_log_caption,
                        disable_web_page_preview=True,
                        reply_markup=log_btn,
                        parse_mode=enums.ParseMode.HTML
                    )
                    if log:
                        log_msg_id = log.id
                except Exception as e:
                    print(f"Log Error: {e}")

                FILE_CACHE[url_hash_id] = {
                    "msg_id": log_msg_id,
                    "name": url_file_name,
                    "ext": ext,
                    "size_str": size_str
                }
                sync_data()

                markup = get_user_buttons(https_link, direct_dl_link, delete_msg_id=log_msg_id, lang=lang)
                await status_msg.edit_text(
                    build_media_card(url_file_name, size_str, ext, http_link, https_link, lang),
                    disable_web_page_preview=True,
                    reply_markup=markup,
                    parse_mode=enums.ParseMode.HTML
                )
    except Exception as e:
        await status_msg.edit_text(
            f"☰ <b>Process Error</b>\n\n⇒ <b>Details :</b>\n├ Error : <code>{str(e)}</code>\n└ Action aborted.",
            parse_mode=enums.ParseMode.HTML
        )


# ==============================================================================
# 🎬 MEDIA INGESTION HANDLER
# ==============================================================================

@TechVJBot.on_message(filters.private & (filters.video | filters.document | filters.audio | filters.photo | filters.voice))
async def handle_media(client, m: Message):
    user = m.from_user
    user_id = user.id

    if user_id in BANNED_USERS:
        msg, btn = build_banned_card(get_user_language(user_id))
        await m.reply_text(msg, reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    ensure_user_record(user)
    lang = get_user_language(user_id)

    file_id = None
    file_unique_id = None
    file_size_raw = 0
    file_ext = "MEDIA"
    file_name = "Media_File"

    if m.photo:
        media = m.photo[-1]
        file_id, file_unique_id, file_size_raw, file_ext, file_name = (
            media.file_id,
            media.file_unique_id,
            getattr(media, "file_size", 0),
            "JPG",
            f"Photo_{media.file_unique_id}.jpg"
        )
    elif m.video:
        media = m.video
        file_id, file_unique_id, file_size_raw = media.file_id, media.file_unique_id, getattr(media, "file_size", 0)
        file_name = getattr(media, "file_name", "") or f"Video_{media.file_unique_id}.mp4"
        file_ext = file_name.split(".")[-1].upper() if "." in file_name else "MP4"
    elif m.document:
        media = m.document
        file_id, file_unique_id, file_size_raw = media.file_id, media.file_unique_id, getattr(media, "file_size", 0)
        file_name = getattr(media, "file_name", "") or f"Doc_{media.file_unique_id}"
        file_ext = file_name.split(".")[-1].upper() if "." in file_name else "DOC"
    elif m.audio:
        media = m.audio
        file_id, file_unique_id, file_size_raw = media.file_id, media.file_unique_id, getattr(media, "file_size", 0)
        file_name = getattr(media, "file_name", "") or f"Audio_{media.file_unique_id}.mp3"
        file_ext = file_name.split(".")[-1].upper() if "." in file_name else "MP3"

    if not file_id:
        return

    status_msg = await m.reply_text(
        build_progress_card(40, "Transferring media...", lang),
        quote=True,
        parse_mode=enums.ParseMode.HTML
    )

    try:
        upload_result = await upload_file_with_retry(file_id)
        raw_name = safe_extract_name(upload_result) or file_name
        hash_val = safe_extract_hash(upload_result)
        encoded_name = safe_quote(raw_name)
        safe_hash = safe_quote(hash_val)

        http_link = f"{HTTP_URL}{upload_result.id}/{encoded_name}?hash={safe_hash}"
        https_link = f"{HTTPS_URL}{upload_result.id}/{encoded_name}?hash={safe_hash}"
        direct_dl_link = f"{HTTPS_URL}dl/{upload_result.id}/{encoded_name}?hash={safe_hash}"
        size_str = humanbytes(file_size_raw)

        admin_log_caption = (
            "☰ <b>GDFlix Media Record (GD-HBX)</b>\n\n"
            "⇒ <b>Upload Details :</b>\n"
            f"├ User : {user.mention}\n"
            f"├ ID   : <code>{user_id}</code>\n"
            f"├ File : <code>{trim_filename(raw_name, 26)}</code>\n"
            f"├ Size : <code>{size_str}</code> (.{file_ext})\n"
            f"└ Ref  : <code>{upload_result.id}</code>\n\n"
            f"<a href=\"{http_link}\">HTTP</a> | <a href=\"{https_link}\">HTTPS</a>"
        )
        admin_markup = get_admin_action_markup(user_id, upload_result.id)

        try:
            await upload_result.edit_caption(
                caption=admin_log_caption,
                reply_markup=admin_markup,
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    admin_log_caption,
                    reply_to_message_id=upload_result.id,
                    reply_markup=admin_markup,
                    disable_web_page_preview=True,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass

        if file_unique_id:
            FILE_CACHE[file_unique_id] = {
                "msg_id": upload_result.id,
                "name": raw_name,
                "hash": hash_val,
                "ext": file_ext,
                "size_str": size_str
            }
            sync_data()

        markup = get_user_buttons(https_link, direct_dl_link, delete_msg_id=upload_result.id, lang=lang)
        await status_msg.edit_text(
            build_media_card(raw_name, size_str, file_ext, http_link, https_link, lang),
            disable_web_page_preview=True,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await status_msg.edit_text(
            f"☰ <b>Upload Error</b>\n\n⇒ <b>Details :</b>\n├ Error : <code>{str(e)}</code>\n└ Operation failed.",
            parse_mode=enums.ParseMode.HTML
        )


# ==============================================================================
# 💬 TEXT INPUT HANDLER
# ==============================================================================

@TechVJBot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "settings", "upload_url", "broadcast", "ban", "unban", "botusers", "restart", "ping"]))
async def handle_text_inputs(client, m: Message):
    user_id = m.from_user.id
    text = m.text.strip()
    ensure_user_record(m.from_user)

    if user_id in WAITING_URL_UPLOAD or text.startswith("http://") or text.startswith("https://"):
        WAITING_URL_UPLOAD.discard(user_id)
        return await process_url_ingestion(client, m, text)

    if user_id in WAITING_BROADCAST and is_authorized(m):
        WAITING_BROADCAST.discard(user_id)
        total_users = len(KNOWN_USERS)
        success = 0
        failed = 0

        prog_card = (
            "☰ <b>GDFlix Transmission</b>\n\n"
            "⇒ <b>Broadcast Queue :</b>\n"
            f"├ Status : <code>In Progress</code>\n"
            f"└ Target : <code>{total_users} Users</code>"
        )
        progress_msg = await m.reply_text(prog_card, parse_mode=enums.ParseMode.HTML)

        for uid_str in list(KNOWN_USERS.keys()):
            try:
                await m.copy(chat_id=int(uid_str))
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.04)

        done_card = (
            "☰ <b>GDFlix Transmission Complete</b>\n\n"
            "⇒ <b>Summary :</b>\n"
            f"├ Total  : <code>{total_users}</code>\n"
            f"├ Sent   : <code>{success}</code>\n"
            f"└ Failed : <code>{failed}</code>"
        )
        await progress_msg.edit_text(done_card, parse_mode=enums.ParseMode.HTML)


# ==============================================================================
# 🔘 INLINE CALLBACK HANDLER
# ==============================================================================

@TechVJBot.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    data = query.data or ""
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    # 1. Real-time Refresh Status Button
    if data == "refresh_status":
        new_text = build_dashboard_text(query.from_user.first_name, lang=user_lang)
        try:
            await query.message.edit_text(
                new_text,
                reply_markup=get_start_markup(user_lang),
                parse_mode=enums.ParseMode.HTML
            )
            await query.answer("System Telemetry Refreshed", show_alert=False)
        except MessageNotModified:
            await query.answer("Already up to date", show_alert=False)
        except Exception:
            await query.answer("Refreshed", show_alert=False)
        return

    # 2. Open Settings via Inline
    if data == "open_settings":
        await query.message.edit_text(
            get_language_selector_text(),
            reply_markup=get_language_markup(),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # 3. Ban Handler (Admin Only + Immune check + Toggle to UNBAN)
    if data.startswith("ban_"):
        if not is_authorized(query):
            await query.answer("Unauthorized access", show_alert=True)
            return

        target_uid = int(data.split("_", 1)[1])
        if target_uid in ADMIN_IDS:
            await query.answer("Notice: Admin cannot be banned.", show_alert=True)
            return

        BANNED_USERS.add(target_uid)
        sync_data()
        await query.answer(f"User {target_uid} has been restricted", show_alert=True)

        try:
            new_markup = query.message.reply_markup
            if new_markup:
                for row in new_markup.inline_keyboard:
                    for btn in row:
                        if btn.callback_data == f"ban_{target_uid}":
                            btn.text = "Unban"
                            btn.callback_data = f"unban_{target_uid}"
                await query.message.edit_reply_markup(new_markup)
        except Exception:
            pass
        return

    # 4. Unban Handler (Admin Only + Toggle to BAN)
    if data.startswith("unban_"):
        if not is_authorized(query):
            await query.answer("Unauthorized access", show_alert=True)
            return

        target_uid = int(data.split("_", 1)[1])
        BANNED_USERS.discard(target_uid)
        sync_data()
        await query.answer(f"User {target_uid} restored", show_alert=True)

        try:
            new_markup = query.message.reply_markup
            if new_markup:
                for row in new_markup.inline_keyboard:
                    for btn in row:
                        if btn.callback_data == f"unban_{target_uid}":
                            btn.text = "Ban"
                            btn.callback_data = f"ban_{target_uid}"
                await query.message.edit_reply_markup(new_markup)
        except Exception:
            pass
        return

    # 5. User Info Card
    if data.startswith("info_"):
        target_uid = data.split("_", 1)[1]
        rec = KNOWN_USERS.get(str(target_uid), {})
        name = rec.get("name", "Unknown")
        user_name = rec.get("username", "None")
        status = "Restricted" if int(target_uid) in BANNED_USERS else "Clean"
        await query.answer(
            f"User : {name}\nAlias : @{user_name}\nID : {target_uid}\nState : {status}",
            show_alert=True
        )
        return

    # 6. Language Selection
    if data in ("lang_hi", "lang_en"):
        selected = "hi" if data == "lang_hi" else "en"
        user = query.from_user
        ensure_user_record(user)
        record = KNOWN_USERS[str(user.id)]
        record["language"] = selected
        sync_data()

        await query.answer("Preference saved", show_alert=False)

        dashboard_text = build_dashboard_text(user.first_name, selected)
        try:
            await query.message.edit_text(
                dashboard_text,
                reply_markup=get_start_markup(selected),
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            pass
        return

    # 7. Delete File from Storage (Bug Fixed)
    if data.startswith("del_"):
        raw_val = data.split("_", 1)[1]
        if raw_val == "url":
            try:
                await query.message.delete()
                await query.answer("Media deleted", show_alert=False)
            except Exception:
                pass
            return

        if raw_val.isdigit():
            target_id = int(raw_val)
            try:
                await client.delete_messages(LOG_CHANNEL, target_id)
                remove_file_from_cache_by_msg_id(target_id)
                sync_data()

                if query.message and query.message.id == target_id:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await query.answer("File permanently deleted", show_alert=True)
                    return

                del_card = (
                    "☰ <b>TgFlix Storage Manager</b>\n\n"
                    "⇒ <b>Notice :</b>\n"
                    "├ Status : <code>Purged</code>\n"
                    "└ File removed from origin log storage."
                )

                if query.message.media:
                    try:
                        await query.message.edit_caption(del_card, parse_mode=enums.ParseMode.HTML)
                    except Exception:
                        await query.message.delete()
                else:
                    await query.message.edit_text(del_card, parse_mode=enums.ParseMode.HTML)

                await query.answer("File deleted", show_alert=False)
            except Exception:
                try:
                    await query.message.delete()
                    await query.answer("File deleted", show_alert=False)
                except Exception as ex:
                    await query.answer(f"Notice: {str(ex)}", show_alert=True)
        else:
            try:
                await query.message.delete()
                await query.answer("Removed", show_alert=False)
            except Exception:
                pass
        return


# ==============================================================================
# 📢 STRICT ADMIN COMMANDS (SILENT / NO-OP FOR NON-ADMINS)
# ==============================================================================

@TechVJBot.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, m: Message):
    if not is_authorized(m):
        return
    WAITING_BROADCAST.add(m.from_user.id)
    card = (
        "☰ <b>Broadcast Interface</b>\n\n"
        "⇒ <b>Action :</b>\n"
        "├ Awaiting next message to broadcast to all records.\n"
        "└ Send any command to dismiss."
    )
    await m.reply_text(card, parse_mode=enums.ParseMode.HTML)


@TechVJBot.on_message(filters.command("botusers") & filters.private)
async def botusers_command(client, m: Message):
    if not is_authorized(m):
        return
    total = len(KNOWN_USERS)
    banned = len(BANNED_USERS)
    uptime_now = get_readable_uptime()
    status_tag = get_status_indicator()

    stats_card = (
        "☰ <b>System Telemetry (GD-HBX)</b>\n\n"
        "⇒ <b>Operational Health :</b>\n"
        f"├ System Status : <code>{status_tag}</code>\n"
        f"├ System Uptime : <code>{uptime_now}</code>\n"
        f"├ Core Engine   : <code>{ENGINE_NAME}</code>\n"
        f"└ Build Release : <code>{BOT_RELEASE}</code>\n\n"
        "⇒ <b>Database Registry :</b>\n"
        f"├ Total Users   : <code>{total}</code>\n"
        f"├ Banned Users  : <code>{banned}</code>\n"
        f"├ Active Users  : <code>{total - banned}</code>\n"
        f"└ Total Admins  : <code>{len(ADMIN_IDS)}</code>"
    )
    await m.reply_text(stats_card, parse_mode=enums.ParseMode.HTML)


@TechVJBot.on_message(filters.command("ban") & filters.private)
async def ban_command(client, m: Message):
    if not is_authorized(m):
        return
    if len(m.command) < 2:
        await m.reply_text("<b>Usage:</b> <code>/ban &lt;user_id&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    try:
        uid = int(m.command[1])
        if uid in ADMIN_IDS:
            await m.reply_text(
                "☰ <b>Security Check</b>\n\n⇒ <b>Denied :</b>\n└ <code>Admin identity cannot be banned.</code>",
                parse_mode=enums.ParseMode.HTML
            )
            return
        BANNED_USERS.add(uid)
        sync_data()
        await m.reply_text(
            f"☰ <b>Access Control</b>\n\n⇒ <b>Notice :</b>\n├ Action : <code>Banned</code>\n└ User ID : <code>{uid}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await m.reply_text(f"Error: <code>{str(e)}</code>", parse_mode=enums.ParseMode.HTML)


@TechVJBot.on_message(filters.command("unban") & filters.private)
async def unban_command(client, m: Message):
    if not is_authorized(m):
        return
    if len(m.command) < 2:
        await m.reply_text("<b>Usage:</b> <code>/unban &lt;user_id&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    try:
        uid = int(m.command[1])
        BANNED_USERS.discard(uid)
        sync_data()
        await m.reply_text(
            f"☰ <b>Access Control</b>\n\n⇒ <b>Notice :</b>\n├ Action : <code>Restored</code>\n└ User ID : <code>{uid}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await m.reply_text(f"Error: <code>{str(e)}</code>", parse_mode=enums.ParseMode.HTML)


@TechVJBot.on_message(filters.command("restart") & filters.private)
async def restart_command(client, m: Message):
    if not is_authorized(m):
        return
    restart_card = (
        "☰ <b>Process Control</b>\n\n"
        "⇒ <b>Rebooting :</b>\n"
        "├ Restarting runtime environment...\n"
        "└ Process will recover shortly."
    )
    await m.reply_text(restart_card, parse_mode=enums.ParseMode.HTML)
    os.execl(sys.executable, sys.executable, *sys.argv)


@TechVJBot.on_message(filters.command("ping") & filters.private)
async def ping_cmd(client, m: Message):
    await m.reply_text(
        f"☰ <b>Latency Check</b>\n\n⇒ <b>Uptime :</b>\n└ <code>{get_readable_uptime()}</code>",
        parse_mode=enums.ParseMode.HTML
    )

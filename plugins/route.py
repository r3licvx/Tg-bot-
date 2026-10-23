# ==============================================================================
# 🚀 BIOSCOPE STREAM ENGINE - ROUTE CORE (Clean File-to-Link)
# ⚡ Ultra Low-Latency Streaming + Anti-Iframe + Direct Download
# ==============================================================================

import asyncio
import logging
import math
import mimetypes
import re
import secrets
from urllib.parse import unquote, urlparse

import aiohttp
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine

from info import *
from TechVJ.bot import multi_clients, work_loads
from TechVJ.server.exceptions import FIleNotFound, InvalidHash
from TechVJ.util.custom_dl import ByteStreamer

routes = web.RouteTableDef()
class_cache = {}

# ==============================================================================
# 📦 MIME TYPES
# ==============================================================================

CUSTOM_MIME_TYPES = {
    # Video
    "mp4": "video/mp4",
    "m4v": "video/x-m4v",
    "webm": "video/webm",
    "ogv": "video/ogg",
    "mov": "video/quicktime",
    "avi": "video/x-msvideo",
    "mkv": "video/x-matroska",
    "mpeg": "video/mpeg",
    "mpg": "video/mpeg",
    "ts": "video/mp2t",
    "3gp": "video/3gpp",

    # Audio
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "opus": "audio/opus",
    "weba": "audio/webm",

    # Images
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "avif": "image/avif",
    "tif": "image/tiff",
    "tiff": "image/tiff",

    # Documents
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "text": "text/plain; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "htm": "text/html; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "js": "text/javascript; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "xml": "application/xml; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",

    # Archives
    "zip": "application/zip",
    "rar": "application/vnd.rar",
    "7z": "application/x-7z-compressed",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

BROWSER_PREVIEW_EXTENSIONS = {
    "mp4", "m4v", "webm", "ogv", "mov", "mpeg", "mpg", "3gp",
    "mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "opus", "weba",
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "avif",
    "tif", "tiff", "pdf", "txt", "text", "html", "htm", "css", "js",
    "json", "xml", "csv", "md"
}

# ==============================================================================
# 🛠 HELPERS
# ==============================================================================

def get_extension(filename: str) -> str:
    filename = filename or ""
    filename = filename.split("?", 1)[0]
    filename = filename.rsplit("/", 1)[-1]
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower().strip()


def get_mime_type(filename="", fallback=None):
    ext = get_extension(filename)
    if ext in CUSTOM_MIME_TYPES:
        return CUSTOM_MIME_TYPES[ext]
    guessed_type, _ = mimetypes.guess_type(filename or "")
    return fallback or guessed_type or "application/octet-stream"


def is_browser_previewable(filename: str, mime_type: str) -> bool:
    ext = get_extension(filename)
    if ext in BROWSER_PREVIEW_EXTENSIONS:
        return True
    mime_type = (mime_type or "").lower()
    return (
        mime_type.startswith("video/")
        or mime_type.startswith("audio/")
        or mime_type.startswith("image/")
        or mime_type.startswith("text/")
        or mime_type in {
            "application/pdf",
            "application/json",
            "application/xml",
            "application/javascript",
        }
    )


def safe_content_disposition(filename: str, inline: bool = True) -> str:
    filename = filename or "media"
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)
    filename = filename.replace('"', "'")
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_name:
        ascii_name = "media"
    disposition = "inline" if inline else "attachment"
    try:
        from urllib.parse import quote
        encoded = quote(filename, safe="")
        return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'
    except Exception:
        return f'{disposition}; filename="{ascii_name}"'


def parse_range_header(range_header: str, file_size: int):
    if not range_header or not range_header.lower().startswith("bytes="):
        return None
    value = range_header[6:].strip()
    if "," in value:
        value = value.split(",", 1)[0].strip()
    if "-" not in value:
        return None
    start_text, end_text = value.split("-", 1)
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return None
            if suffix_length >= file_size:
                return 0, file_size - 1
            return file_size - suffix_length, file_size - 1
        start = int(start_text)
        if start < 0 or start >= file_size:
            return None
        if not end_text:
            end = file_size - 1
        else:
            end = int(end_text)
        if end < start:
            return None
        end = min(end, file_size - 1)
        return start, end
    except (TypeError, ValueError):
        return None


def add_common_headers(headers):
    headers.update({
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, Origin, Accept",
        "Access-Control-Expose-Headers": (
            "Accept-Ranges, Content-Length, Content-Range, Content-Type, Content-Disposition"
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=3600",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none';",
        "X-Download-Options": "noopen",
    })


# ==============================================================================
# 🌐 ROOT & OPTIONS
# ==============================================================================

@routes.options("/{path:.*}")
async def options_handler(request: web.Request):
    headers = {}
    add_common_headers(headers)
    return web.Response(status=204, headers=headers)


@routes.get("/", allow_head=True)
async def root_route_handler(request: web.Request):
    return web.json_response({
        "status": "Online",
        "engine": "Bioscope Stream Engine",
        "version": "Clean v50.0",
        "streaming": "enabled"
    })


# ==============================================================================
# 🌐 DIRECT WEB URL PROXY
# ==============================================================================

@routes.get("/url", allow_head=True)
async def url_stream_proxy(request: web.Request):
    src_url = request.rel_url.query.get("src")
    is_download = request.rel_url.query.get("download") == "1"

    if not src_url:
        raise web.HTTPBadRequest(text="Missing URL parameter 'src'")

    target_url = unquote(src_url).strip()
    parsed = urlparse(target_url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise web.HTTPBadRequest(text="Only HTTP/HTTPS URLs are supported")

    clean_path = parsed.path or ""
    ext = get_extension(clean_path)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"

    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": f"{target_origin}/",
        "Origin": target_origin,
        "Accept": "*/*",
        "Sec-Fetch-Mode": "cors",
    }

    range_header = request.headers.get("Range")
    if range_header:
        req_headers["Range"] = range_header

    session = None
    resp = None

    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15, sock_read=None)
        session = aiohttp.ClientSession(timeout=timeout)
        resp = await session.get(target_url, headers=req_headers, allow_redirects=True)

        source_content_type = resp.headers.get("Content-Type") or ""
        mime_type = get_mime_type(clean_path, source_content_type)

        if mime_type == "application/octet-stream" and ext in CUSTOM_MIME_TYPES:
            mime_type = CUSTOM_MIME_TYPES[ext]

        inline = False if is_download else is_browser_previewable(clean_path, mime_type)

        out_headers = {
            "Content-Type": "application/octet-stream" if is_download else mime_type,
            "Content-Disposition": safe_content_disposition(
                clean_path.rsplit("/", 1)[-1] or "media",
                inline=inline
            ),
        }

        if "Content-Length" in resp.headers:
            out_headers["Content-Length"] = resp.headers["Content-Length"]

        if "Content-Range" in resp.headers:
            out_headers["Content-Range"] = resp.headers["Content-Range"]

        add_common_headers(out_headers)
        response = web.StreamResponse(status=resp.status, headers=out_headers)
        await response.prepare(request)

        if request.method == "HEAD":
            resp.release()
            await session.close()
            return response

        async for chunk in resp.content.iter_chunked(1024 * 512):
            await response.write(chunk)

        await response.write_eof()
        resp.release()
        await session.close()
        return response

    except Exception as e:
        if resp is not None:
            resp.release()
        if session and not session.closed:
            await session.close()
        logging.exception("URL Proxy Stream Error: %s", e)
        raise web.HTTPInternalServerError(text="Failed to stream target URL")


# ==============================================================================
# 🎬 DIRECT DOWNLOAD & STREAM ROUTES FOR TELEGRAM FILES
# ==============================================================================

@routes.get(r"/dl/{path:\S+}", allow_head=True)
async def direct_download_handler(request: web.Request):
    return await handle_telegram_stream(request, force_download=True)


@routes.get(r"/{path:\S+}", allow_head=True)
async def media_handler(request: web.Request):
    return await handle_telegram_stream(request, force_download=False)


async def handle_telegram_stream(request: web.Request, force_download: bool = False):
    try:
        path = request.match_info["path"]
        match = re.search(r"^(\d+)", path)

        if not match:
            raise FIleNotFound

        file_message_id = int(match.group(1))
        secure_hash = request.rel_url.query.get("hash")

        return await media_streamer(
            request,
            file_message_id,
            secure_hash,
            force_download=force_download
        )

    except InvalidHash:
        raise web.HTTPForbidden(text="Invalid Security Token")
    except FIleNotFound:
        raise web.HTTPNotFound(text="File not found or deleted")
    except Exception as e:
        logging.exception("Media Handler Error: %s", e)
        raise web.HTTPInternalServerError(text="Internal streaming error")


# ==============================================================================
# 🚀 TELEGRAM STREAMER
# ==============================================================================

async def media_streamer(
    request: web.Request,
    id: int,
    secure_hash: str = None,
    force_download: bool = False
):
    range_header = request.headers.get("Range")
    index = min(work_loads, key=work_loads.get)
    client = multi_clients[index]
    work_loads[index] += 1

    try:
        if client in class_cache:
            tg = class_cache[client]
        else:
            tg = ByteStreamer(client)
            class_cache[client] = tg

        file_id = await tg.get_file_properties(id)

        if secure_hash and file_id.unique_id[:6] != secure_hash:
            raise InvalidHash

        file_size = int(file_id.file_size or 0)
        if file_size <= 0:
            raise FIleNotFound

        file_name = file_id.file_name or f"{secrets.token_hex(4)}.mp4"
        ext = get_extension(file_name)
        source_mime = getattr(file_id, "mime_type", None) or ""
        mime_type = get_mime_type(file_name, source_mime)

        if mime_type == "application/octet-stream" and ext in CUSTOM_MIME_TYPES:
            mime_type = CUSTOM_MIME_TYPES[ext]

        inline = False if force_download else is_browser_previewable(file_name, mime_type)
        parsed_range = parse_range_header(range_header, file_size)

        if range_header and parsed_range is None:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}", "Accept-Ranges": "bytes"},
            )

        if parsed_range:
            start, end = parsed_range
            status = 206
        else:
            start = 0
            end = file_size - 1
            status = 200

        content_length = end - start + 1
        chunk_size = 1024 * 512
        offset = start - (start % chunk_size)
        first_cut = start - offset
        last_cut = (end % chunk_size) + 1
        part_count = math.ceil((end + 1) / chunk_size) - math.floor(offset / chunk_size)

        body = tg.yield_file(
            file_id,
            index,
            offset,
            first_cut,
            last_cut,
            part_count,
            chunk_size,
        )

        headers = {
            "Content-Type": "application/octet-stream" if force_download else mime_type,
            "Content-Length": str(content_length),
            "Content-Disposition": safe_content_disposition(file_name, inline=inline),
        }

        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        add_common_headers(headers)
        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        if request.method == "HEAD":
            return response

        async for chunk in body:
            if not chunk:
                continue
            await response.write(chunk)

        await response.write_eof()
        return response

    finally:
        work_loads[index] -= 1

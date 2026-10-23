import re
from os import environ

id_pattern = re.compile(r'^.\d+$')

# ---------------- BOT INFORMATION ----------------
SESSION = environ.get('SESSION', 'Rs_link_bots')
API_ID = int(environ.get('API_ID', 30573240))
API_HASH = environ.get('API_HASH', "c877f946e8739d3c08d5b70332342ee2")

# Tera Bot Token:
BOT_TOKEN = environ.get("BOT_TOKEN", "8900284739:AAFSXuZPun57Uada06JHUX6CMhZL1mn1ynk")

# ---------------- SERVER SETTINGS ----------------
PORT = int(environ.get("PORT", 8080))
MULTI_CLIENT = True
SLEEP_THRESHOLD = int(environ.get('SLEEP_THRESHOLD', 60))
PING_INTERVAL = int(environ.get("PING_INTERVAL", 1200))

# ---------------- HEROKU CHECK ----------------
ON_HEROKU = 'DYNO' in environ

# ---------------- STREAM BASE URLS ----------------
HTTP_URL = environ.get('HTTP_URL', "http://fi16.bot-hosting.cloud:25149/")
HTTPS_URL = environ.get('HTTPS_URL', "https://filetolink21.apps.bot-hosting.cloud/")
URL = HTTPS_URL

# ---------------- ADMINS & CHANNELS ----------------
LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-1004263921877'))

ADMINS = [int(admin) for admin in environ.get('ADMINS', '7475029864').split()]

# ---------------- DATABASE ----------------
DATABASE_URI = environ.get(
    'DATABASE_URI', 
    "mongodb+srv://suryavirkumar545_db_user:7GvnTTVPGhQeVZAt@suryavir.8zdapdb.mongodb.net/?appName=Suryavir"
)
DATABASE_NAME = environ.get('DATABASE_NAME', "rs_fllink_bot")

# ---------------- SHORTLINK ----------------
SHORTLINK = environ.get('SHORTLINK', 'False').lower() in ('true', '1')
SHORTLINK_URL = environ.get('SHORTLINK_URL', 'api.shareus.io')
SHORTLINK_API = environ.get('SHORTLINK_API', 'hRPS5vvZc0OGOEUQJMJzPiojoVK2')

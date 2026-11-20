# -*- coding: utf-8 -*-
import os
import re
import json
import html
import logging
from datetime import datetime, timezone, timedelta
import phonenumbers
from phonenumbers import geocoder

logger = logging.getLogger("Config")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Default configuration
DEFAULT_CONFIG = {
    "portal_base_url": "http://168.119.13.175/ints",
    "accounts": [
        {
            "username": "Atiar59_FD",
            "password": "Atiar5942@#"
        },
        {
            "username": "Smswork21_FD",
            "password": "Smswork21_FD"
        }
    ],
    "default_keyword": "Telegram",
    "bot_token": "8784442674:AAE-nwM7m7svAL9nxipswL8f6CwvssKfIyc",
    "group_id": "-1003996842463",
    "poll_interval_sec": 0.3,
    "display_length": 75,
    "web_port": 5000
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(user_cfg)
                return cfg
        except Exception as e:
            logger.error(f"Error loading {CONFIG_FILE}: {e}")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {CONFIG_FILE}: {e}")
        return False

# Global Country Mapping & Cache
COUNTRY_CACHE = {}

CALLING_CODE_TO_ISO = {
    "1": "US", "7": "RU", "20": "EG", "27": "ZA", "30": "GR", "31": "NL", "32": "BE", "33": "FR",
    "34": "ES", "36": "HU", "39": "IT", "40": "RO", "41": "CH", "43": "AT", "44": "GB", "45": "DK",
    "46": "SE", "47": "NO", "48": "PL", "49": "DE", "51": "PE", "52": "MX", "53": "CU", "54": "AR",
    "55": "BR", "56": "CL", "57": "CO", "58": "VE", "60": "MY", "61": "AU", "62": "ID", "63": "PH",
    "64": "NZ", "65": "SG", "66": "TH", "81": "JP", "82": "KR", "84": "VN", "86": "CN", "90": "TR",
    "91": "IN", "92": "PK", "93": "AF", "94": "LK", "95": "MM", "98": "IR", "212": "MA", "213": "DZ",
    "216": "TN", "218": "LY", "220": "GM", "221": "SN", "222": "MR", "223": "ML", "224": "GN",
    "225": "CI", "226": "BF", "227": "NE", "228": "TG", "229": "BJ", "230": "MU", "231": "LR",
    "232": "SL", "233": "GH", "234": "NG", "235": "TD", "236": "CF", "237": "CM", "238": "CV",
    "239": "ST", "240": "GQ", "241": "GA", "242": "CG", "243": "CD", "244": "AO", "245": "GW",
    "248": "SC", "249": "SD", "250": "RW", "251": "ET", "252": "SO", "253": "DJ", "254": "KE",
    "255": "TZ", "256": "UG", "257": "BI", "258": "MZ", "260": "ZM", "261": "MG", "262": "RE",
    "263": "ZW", "264": "NA", "265": "MW", "266": "LS", "267": "BW", "268": "SZ", "269": "KM",
    "290": "SH", "291": "ER", "297": "AW", "298": "FO", "299": "GL", "350": "GI", "351": "PT",
    "352": "LU", "353": "IE", "354": "IS", "355": "AL", "356": "MT", "357": "CY", "358": "FI",
    "359": "BG", "370": "LT", "371": "LV", "372": "EE", "373": "MD", "374": "AM", "375": "BY",
    "376": "AD", "377": "MC", "378": "SM", "380": "UA", "381": "RS", "382": "ME", "385": "HR",
    "386": "SI", "387": "BA", "389": "MK", "420": "CZ", "421": "SK", "423": "LI", "850": "KP",
    "852": "HK", "853": "MO", "855": "KH", "856": "LA", "880": "BD", "960": "MV", "961": "LB",
    "962": "JO", "963": "SY", "964": "IQ", "965": "KW", "966": "SA", "967": "YE", "968": "OM",
    "970": "PS", "971": "AE", "972": "IL", "973": "BH", "974": "QA", "975": "BT", "976": "MN",
    "977": "NP", "992": "TJ", "993": "TM", "994": "AZ", "995": "GE", "996": "KG", "998": "UZ"
}

def get_country_info(phone):
    """Resolves country name, flag emoji, and calling code."""
    clean = re.sub(r'[^0-9]', '', str(phone))
    if not clean:
        return "Unknown", "XX", "🌐", ""

    pfx_cache = clean[:5]
    if pfx_cache in COUNTRY_CACHE:
        return COUNTRY_CACHE[pfx_cache]

    iso = None
    name = None
    calling_code = ""

    try:
        p = phonenumbers.parse("+" + clean)
        calling_code = str(p.country_code)
        iso = phonenumbers.region_code_for_number(p) or phonenumbers.region_code_for_country_code(p.country_code)
        name = geocoder.country_name_for_number(p, "en")
    except Exception:
        pass

    if not name or name.startswith("Code +"):
        for plen in (4, 3, 2, 1):
            sub = clean[:plen]
            if sub in CALLING_CODE_TO_ISO:
                iso = CALLING_CODE_TO_ISO[sub]
                calling_code = sub
                name = f"Country +{sub}"
                break

    if not iso or iso == "XX":
        iso = "XX"
        flag = "🌐"
        if not name:
            name = f"Country +{clean[:3]}"
    else:
        iso = iso.upper()
        if len(iso) == 2:
            flag = "".join(chr(127397 + ord(c)) for c in iso)
        else:
            flag = "🌐"

    if not name:
        name = f"Country +{calling_code or clean[:3]}"

    res = (name, iso, flag, calling_code or clean[:3])
    COUNTRY_CACHE[pfx_cache] = res
    return res

def extract_otp(text, cli=""):
    """Multi-pattern OTP code extractor."""
    if not text:
        return ""
    raw = str(text).strip()

    # 1. 'code [is|:]? <digits>' or 'codigo [de|es|:]? <digits>'
    m = re.search(r'(?:code|codigo|código|verification|kod|pin|otp)\s*(?:is|es|de|:)?\s*[:#]?\s*([0-9]{4,8}|[0-9]{3}[-\s][0-9]{3})\b', raw, re.IGNORECASE)
    if m:
        return m.group(1).replace(' ', '').replace('-', '')

    # 2. Login URL link: login12345 or httpstmelogin12345
    m_login = re.search(r'login(\d{4,6})', raw, re.IGNORECASE)
    if m_login:
        return m_login.group(1)

    # 3. Leading '# 123456' or '123456 is your Telegram code'
    m_lead = re.search(r'(?:^|#\s*)([0-9]{4,8}|[0-9]{3}[-\s][0-9]{3})\s*(?:is|es|to|for|es tu)\b', raw, re.IGNORECASE)
    if m_lead:
        return m_lead.group(1).replace(' ', '').replace('-', '')

    # 4. 'Telegram code 12345'
    m_tg = re.search(r'Telegram\s+code\s*[:\s]*(\d{4,6})', raw, re.IGNORECASE)
    if m_tg:
        return m_tg.group(1)

    # 5. WhatsApp / Google / Viber
    m_dash = re.search(r'\b([A-Z]-)?([0-9]{3}[-][0-9]{3})\b', raw)
    if m_dash:
        return m_dash.group(2).replace('-', '')

    # 6. Standalone 4 to 8 digit number
    candidates = re.findall(r'(?<!\d)([0-9]{4,8})(?!\d)', raw)
    if candidates:
        for c in candidates:
            if c not in ("2024", "2025", "2026", "2027"):
                return c
        return candidates[0]

    return ""

def format_telegram_message(phone, country_name, flag, cli, otp, raw_msg, panel_time, delivery_time, speed_str="⚡ Instant (0ms)", keyword="Telegram"):
    """Formats the Telegram message identical to TG BABA style."""
    clean_p = re.sub(r'[^0-9]', '', str(phone))
    num_display = f"+{clean_p}"

    text = (
        f"📩 <b>New SMS Received</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Panel Time:</b> <code>{panel_time}</code>\n"
        f"⚡ <b>Delivery Time:</b> <code>{delivery_time}</code>\n"
        f"⏳ <b>Speed:</b> <code>{speed_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Country:</b> {flag} <b>{country_name}</b>\n"
        f"📱 <b>Number:</b> <code>{num_display}</code>\n"
        f"🏷 <b>CLI:</b> <b>{cli}</b>\n"
    )
    if otp:
        text += f"🔑 <b>OTP:</b> <code>{html.escape(str(otp))}</code>\n"
    text += (
        f"💬 <b>Message:</b>\n"
        f"<blockquote>{html.escape(raw_msg)}</blockquote>\n"
    )
    if keyword:
        text += f"🔍 <b>Keyword:</b> <code>{html.escape(keyword)}</code>\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━"
    return text

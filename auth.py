"""
حسابات المستخدمين — كل مستخدم له اسم دخول وكلمة مرور خاصة به، وبيانات جدوله
منفصلة تماماً عن بقية المستخدمين (راجع ``persistence.user_data_file``).

تنبيه أمني مهم
---------------
هذا نظام تسجيل دخول **بسيط** مناسب لفريق صغير (مدرسة، إدارة واحدة...)، وليس
نظاماً أمنياً كاملاً لموقع عام مفتوح للجميع:
- لا يوجد تحقق من البريد الإلكتروني ولا استرجاع لكلمة مرور منسية.
- لا يوجد حد لعدد محاولات الدخول الخاطئة (brute-force protection).
- كلمات المرور تُشفَّر (لا تُحفظ نصاً صريحاً) لكن الملف الذي يحوي التشفير
  (``users.json``) **يجب ألا يُرفع لمستودع GitHub عام** — أضفه إلى
  ``.gitignore`` (موجود جاهزاً في هذا المشروع).
"""

import hashlib
import json
import re
import secrets

from applog import logger
from constants import USERS_FILE

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,20}$")
MIN_PASSWORD_LENGTH = 6


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.match(username or ""))


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("تعذّرت قراءة %s.", USERS_FILE)
        return {}


def _save_users(users: dict) -> None:
    USERS_FILE.write_text(
        json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    ).hex()


def create_user(username: str, password: str) -> tuple[bool, str]:
    """ينشئ حساباً جديداً. يعيد (نجح, رسالة الخطأ إن فشل)."""
    username = (username or "").strip()
    if not is_valid_username(username):
        return False, (
            "اسم المستخدم يجب أن يكون بين 3 و20 حرفاً/رقماً "
            "(يُسمح أيضاً بـ _ و- وبدون مسافات)."
        )
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return False, f"كلمة المرور يجب أن تكون {MIN_PASSWORD_LENGTH} أحرف على الأقل."

    users = _load_users()
    if username in users:
        return False, "اسم المستخدم محجوز بالفعل، اختر اسماً آخر."

    is_first_user = len(users) == 0
    salt = secrets.token_hex(16)
    users[username] = {"salt": salt, "hash": _hash_password(password, salt)}
    _save_users(users)

    if is_first_user:
        _migrate_legacy_data(username)

    return True, ""


def verify_login(username: str, password: str) -> bool:
    users = _load_users()
    record = users.get((username or "").strip())
    if not record:
        return False
    expected_hash = record.get("hash", "")
    computed_hash = _hash_password(password or "", record.get("salt", ""))
    return secrets.compare_digest(computed_hash, expected_hash)


def _migrate_legacy_data(username: str) -> None:
    """ينسخ بيانات ``saved_data.json`` القديمة (قبل إضافة الحسابات) لأول
    حساب يُنشأ، حتى لا تضيع الجداول التي أُدخلت قبل هذا التحديث.
    """
    import persistence
    from constants import DATA_FILE

    if not DATA_FILE.exists():
        return
    target = persistence.user_data_file(username)
    if target.exists():
        return
    try:
        target.write_text(DATA_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("تم ترحيل بيانات saved_data.json القديمة إلى الحساب %s.", username)
    except Exception:
        logger.exception("تعذّر ترحيل البيانات القديمة إلى الحساب %s.", username)

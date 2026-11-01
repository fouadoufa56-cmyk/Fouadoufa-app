"""
حسابات المستخدمين — كل مستخدم له اسم دخول وكلمة مرور خاصة به، وبيانات جدوله
منفصلة تماماً عن بقية المستخدمين.

كل القراءة والكتابة تمر عبر ``storage.py`` (ملفات محلية أو Supabase).

تنبيه أمني مهم
---------------
هذا نظام تسجيل دخول **بسيط** مناسب لفريق صغير (مدرسة، إدارة واحدة...)، وليس
نظاماً أمنياً كاملاً لموقع عام مفتوح للجميع:
- لا يوجد تحقق من البريد الإلكتروني ولا استرجاع لكلمة مرور منسية.
- لا يوجد حد لعدد محاولات الدخول الخاطئة (brute-force protection).
- كلمات المرور تُشفَّر (لا تُحفظ نصاً صريحاً). ملفات ``users.json`` و``sessions.json``
  و``user_data/`` **يجب ألا تُرفع لمستودع GitHub عام** (موجودة في ``.gitignore``).
"""

import hashlib
import json
import re
import secrets
import time

import storage
from applog import logger
from constants import DATA_FILE, MAX_ACCOUNTS, SESSION_DAYS

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,20}$")
MIN_PASSWORD_LENGTH = 6


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.match(username or ""))


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    ).hex()


def can_create_more() -> bool:
    """هل ما زال مسموحاً إنشاء حساب جديد (لم نبلغ ``MAX_ACCOUNTS``)؟"""
    return storage.count_keys("users") < MAX_ACCOUNTS


def create_user(username: str, password: str) -> tuple[bool, str]:
    """ينشئ حساباً جديداً. يعيد (نجح, رسالة الخطأ إن فشل).

    قد يرفع ``storage.StorageError`` لو تعذّر الوصول لمكان التخزين.
    """
    username = (username or "").strip()
    if not is_valid_username(username):
        return False, (
            "اسم المستخدم يجب أن يكون بين 3 و20 حرفاً/رقماً "
            "(يُسمح أيضاً بـ _ و- وبدون مسافات)."
        )
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return False, f"كلمة المرور يجب أن تكون {MIN_PASSWORD_LENGTH} أحرف على الأقل."

    if storage.get("users", username) is not None:
        return False, "اسم المستخدم محجوز بالفعل، اختر اسماً آخر."
    if not can_create_more():
        return False, f"تم بلوغ الحد الأقصى للحسابات ({MAX_ACCOUNTS})."

    is_first_user = not storage.any_keys("users")
    salt = secrets.token_hex(16)
    storage.put("users", username, {"salt": salt, "hash": _hash_password(password, salt)})

    if is_first_user:
        _migrate_legacy_data(username)

    return True, ""


def verify_login(username: str, password: str) -> bool:
    record = storage.get("users", (username or "").strip())
    if not record:
        return False
    expected_hash = record.get("hash", "")
    computed_hash = _hash_password(password or "", record.get("salt", ""))
    return secrets.compare_digest(computed_hash, expected_hash)


def get_account_record(username: str) -> dict | None:
    """بصمة الحساب المحفوظة (salt + hash) — تُنسخ إلى سجل المتصفح."""
    record = storage.get("users", username)
    if isinstance(record, dict) and record.get("salt") and record.get("hash"):
        return {"salt": record["salt"], "hash": record["hash"]}
    return None


def restore_account(username: str, password: str, record) -> bool:
    """يعيد إنشاء حساب فُقد من السيرفر، من نسخة محفوظة بمتصفح صاحبه.

    يشترط أن تكون كلمة المرور صحيحة (تُطابَق مع البصمة المحفوظة بالمتصفح)، وألا
    يكون الحساب موجوداً بالسيرفر (لا نكتب فوق حساب موجود).
    """
    username = (username or "").strip()
    if not is_valid_username(username) or not isinstance(record, dict):
        return False
    salt, expected = record.get("salt"), record.get("hash")
    if not salt or not expected:
        return False
    if storage.get("users", username) is not None or not can_create_more():
        return False
    if not secrets.compare_digest(_hash_password(password or "", salt), expected):
        return False
    storage.put("users", username, {"salt": salt, "hash": expected})
    logger.info("أُعيد إنشاء الحساب %s من سجل المتصفح.", username)
    return True


# ─── جلسات الدخول الدائمة (تبقى بعد تحديث الصفحة) ───────────────────────────
# عند الدخول نُنشئ رمزاً عشوائياً طويلاً: نحفظ نسخته المشفّرة (SHA-256) في
# التخزين، ونضع الرمز نفسه في كوكي بمتصفح المستخدم. عند فتح الصفحة (أو
# تحديثها) نقرأ الكوكي ونطابقه فنُرجع المستخدم مسجَّلاً. الخروج يحذف الرمز
# فيبطل مفعوله فوراً.


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def create_session(username: str) -> str:
    """ينشئ جلسة دائمة للمستخدم ويعيد الرمز الذي يوضع في الكوكي."""
    token = secrets.token_urlsafe(32)
    storage.put(
        "sessions",
        _hash_token(token),
        {"user": username, "expires": time.time() + SESSION_DAYS * 86400},
    )
    return token


def validate_session(token: str | None) -> str | None:
    """يعيد اسم المستخدم لو الرمز صالح وغير منتهٍ، وإلا None."""
    if not token:
        return None
    key = _hash_token(token)
    record = storage.get("sessions", key)
    if not record:
        return None
    if record.get("expires", 0) <= time.time():
        storage.delete("sessions", key)
        return None
    # الحساب قد يكون حُذف بعد إنشاء الجلسة
    return record["user"] if storage.get("users", record.get("user", "")) else None


def delete_session(token: str | None) -> None:
    if token:
        storage.delete("sessions", _hash_token(token))


def _migrate_legacy_data(username: str) -> None:
    """ينسخ بيانات ``saved_data.json`` القديمة (قبل إضافة الحسابات) لأول
    حساب يُنشأ، حتى لا تضيع الجداول التي أُدخلت قبل هذا التحديث.
    """
    if not DATA_FILE.exists() or storage.get("data", username) is not None:
        return
    try:
        storage.put("data", username, json.loads(DATA_FILE.read_text(encoding="utf-8")))
        logger.info("تم ترحيل بيانات saved_data.json القديمة إلى الحساب %s.", username)
    except Exception:
        logger.exception("تعذّر ترحيل البيانات القديمة إلى الحساب %s.", username)

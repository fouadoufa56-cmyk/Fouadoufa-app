"""
طبقة التخزين — المكان الوحيد الذي يقرأ ويكتب بيانات التطبيق (الحسابات،
الجلسات، جداول كل مستخدم).

وضعان، يُختاران تلقائياً:

1) **ملفات محلية** (الافتراضي): ``users.json`` و``sessions.json`` و``user_data/``.
   مناسب لتشغيل التطبيق على جهازك، حيث تبقى الملفات على قرصك.

2) **Supabase** (قاعدة بيانات مجانية على الإنترنت): يُفعَّل لو وُجد قسم
   ``[supabase]`` في أسرار Streamlit (url و key). مناسب للنشر على سيرفر مثل
   Streamlit Cloud، لأن قرص السيرفر هناك **مؤقت** وتُمسح ملفاته عند إعادة
   التشغيل، بينما القاعدة الخارجية تحفظ بياناتك دائماً.

الأقسام (ns): ``users`` و``sessions`` و``data``. كل سجل له مفتاح (key) وقيمة JSON.
لا مكتبات إضافية: الاتصال بـ Supabase عبر مكتبة بايثون القياسية فقط.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from applog import logger
from constants import DATA_DIR, SESSIONS_FILE, USERS_FILE
from file_lock import locked

_SAFE = re.compile(r"[^A-Za-z0-9_\-]")
_TABLE = "app_store"


class StorageError(Exception):
    """فشلت القراءة/الكتابة (غير «غير موجود»: الموجود الفارغ يُرجع None)."""


# ═══════════════════════════════════════════════════════════════════════════
# ملفات محلية
# ═══════════════════════════════════════════════════════════════════════════
class LocalBackend:
    name = "local"

    @staticmethod
    def _dict_file(ns):
        return {"users": USERS_FILE, "sessions": SESSIONS_FILE}.get(ns)

    @staticmethod
    def _data_file(key):
        safe = _SAFE.sub("", key or "") or "user"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / f"{safe}.json"

    @staticmethod
    def _lock(path):
        return locked(path.with_name(f".{path.stem}.lock"))

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.exception("تعذّرت قراءة %s.", path)
            raise StorageError(f"تعذّرت قراءة الملف {path.name}") from exc

    def get(self, ns, key):
        path = self._data_file(key) if ns == "data" else self._dict_file(ns)
        if not path.exists():
            return None
        with self._lock(path):
            content = self._read(path)
        return content if ns == "data" else content.get(key)

    def put(self, ns, key, value):
        try:
            if ns == "data":
                path = self._data_file(key)
                with self._lock(path):
                    path.write_text(
                        json.dumps(value, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                return
            path = self._dict_file(ns)
            with self._lock(path):
                content = self._read(path) if path.exists() else {}
                content[key] = value
                if ns == "sessions":  # تنظيف الجلسات المنتهية
                    now = time.time()
                    content = {
                        k: v for k, v in content.items() if v.get("expires", 0) > now
                    }
                path.write_text(
                    json.dumps(content, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except StorageError:
            raise
        except Exception as exc:
            logger.exception("تعذّرت الكتابة في %s/%s.", ns, key)
            raise StorageError("تعذّرت الكتابة على القرص") from exc

    def delete(self, ns, key):
        path = self._dict_file(ns)
        if path is None or not path.exists():
            return
        with self._lock(path):
            content = self._read(path)
            if content.pop(key, None) is not None:
                path.write_text(
                    json.dumps(content, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    def any_keys(self, ns):
        path = self._dict_file(ns)
        if path is None or not path.exists():
            return False
        with self._lock(path):
            return bool(self._read(path))


# ═══════════════════════════════════════════════════════════════════════════
# Supabase (REST عبر urllib)
# ═══════════════════════════════════════════════════════════════════════════
class RemoteBackend:
    name = "supabase"

    def __init__(self, url, key):
        self.base = url.rstrip("/") + f"/rest/v1/{_TABLE}"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_"):  # المفاتيح الجديدة (sb_...) ليست JWT فلا تُرسل كـ Bearer
            self.headers["Authorization"] = f"Bearer {key}"

    def _call(self, method, query="", body=None, extra=None):
        headers = {**self.headers, **(extra or {})}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.base}{query}", data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            logger.error("Supabase %s %s -> %s %s", method, query, exc.code, detail)
            raise StorageError(f"رفض الخادم الطلب (رمز {exc.code})") from exc
        except Exception as exc:
            logger.exception("تعذّر الاتصال بـ Supabase.")
            raise StorageError("تعذّر الاتصال بقاعدة البيانات") from exc
        return json.loads(raw) if raw.strip() else None

    @staticmethod
    def _where(ns, key=None):
        q = f"?ns=eq.{urllib.parse.quote(ns, safe='')}"
        if key is not None:
            q += f"&key=eq.{urllib.parse.quote(key, safe='')}"
        return q

    def get(self, ns, key):
        rows = self._call("GET", self._where(ns, key) + "&select=value")
        return rows[0]["value"] if rows else None

    def put(self, ns, key, value):
        self._call(
            "POST",
            "?on_conflict=ns,key",
            body={"ns": ns, "key": key, "value": value},
            extra={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def delete(self, ns, key):
        self._call("DELETE", self._where(ns, key), extra={"Prefer": "return=minimal"})

    def any_keys(self, ns):
        return bool(self._call("GET", self._where(ns) + "&select=key&limit=1"))


# ═══════════════════════════════════════════════════════════════════════════
# اختيار الوضع
# ═══════════════════════════════════════════════════════════════════════════
_backend = None


def _make_backend():
    try:
        import streamlit as st

        cfg = st.secrets["supabase"]
        url, key = str(cfg["url"]).strip(), str(cfg["key"]).strip()
        if url and key:
            return RemoteBackend(url, key)
    except Exception:
        pass  # لا توجد أسرار Supabase: نستخدم الملفات المحلية
    return LocalBackend()


def backend():
    global _backend
    if _backend is None:
        _backend = _make_backend()
    return _backend


def get(ns, key):
    return backend().get(ns, key)


def put(ns, key, value):
    backend().put(ns, key, value)


def delete(ns, key):
    backend().delete(ns, key)


def any_keys(ns):
    return backend().any_keys(ns)

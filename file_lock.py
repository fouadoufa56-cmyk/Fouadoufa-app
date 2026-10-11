"""
قفل ملف بسيط (advisory file lock) يمنع تلف ``saved_data.json`` لو حاول
مستخدمان الحفظ في نفس اللحظة بالضبط.

هذا لا يحل مشكلة أن الملف *مشترك* بين كل المستخدمين (راجع التنبيه في
``persistence.py`` و README) — فقط يمنع أن يكتب اثنان فوق بعض بنفس اللحظة
فيتلف الملف بأكمله ويصبح غير قابل للقراءة.

نستخدم ``fcntl`` (متوفرة على أنظمة Linux وmacOS، وهذا ما تعمل عليه أغلب
منصات النشر مثل Streamlit Community Cloud). على Windows أثناء التطوير
المحلي لا تتوفر ``fcntl``، فنكتفي بدون قفل حقيقي حتى لا يتعطل التطبيق —
وهذا مقبول لأن التطوير المحلي عادة من شخص واحد فقط في نفس اللحظة.
"""

import contextlib
from pathlib import Path

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # على Windows
    _HAS_FCNTL = False


@contextlib.contextmanager
def locked(lock_path: Path):
    """يستخدم هكذا: ``with locked(lock_path): ...قراءة أو كتابة الملف..."""
    if not _HAS_FCNTL:
        yield
        return
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

"""
تسجيل بسيط للأخطاء غير المتوقعة في ملف ``app_errors.log``.

قبل هذا الملف كانت أخطاء كثيرة تُبلع بصمت بـ ``except Exception: pass``.
هذا مريح للمستخدم (لا تتعطل الصفحة لأجل خطأ بسيط)، لكنه يجعل تشخيص أي مشكلة
مستحيلاً لاحقاً. الحل هنا وسط: نُبقي التطبيق يعمل رغم الخطأ (لا نوقفه)، لكن
نسجّل تفاصيل كل خطأ في ملف نصي بجانب التطبيق حتى تقدر ترجع له لاحقاً.
"""

import logging
from pathlib import Path

_LOG_FILE = Path(__file__).parent / "app_errors.log"

logger = logging.getLogger("timetable_app")
if not logger.handlers:  # يمنع تكرار الإعداد عند كل إعادة تشغيل لسكربت Streamlit
    logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)

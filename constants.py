"""
ثوابت التطبيق الثابتة (لا تتغيّر أثناء التشغيل ولا تعتمد على session_state).
أي قيمة هنا آمنة الاستيراد من أي وحدة أخرى دون خطر حلقات استيراد.
"""

from pathlib import Path

# ─── الصفحات (السنوات / التخصصات) ───────────────────────────────────────────
DEFAULT_PAGE_COUNT = 3
DEFAULT_PAGE_NAMES = {
    "1": "السنة الأولى",
    "2": "السنة الثانية",
    "3": "السنة الثالثة",
}
DEFAULT_PAGE = "2"

# ─── المواد والأساتذة الافتراضيون (تُستخدم أول مرة فقط) ─────────────────────
LEGACY_COURSES_DATA = {
    "-- فارغ --": [],
    "RDM": ["Pr. ALAMI", "Pr. BENNANI"],
    "MEC DES SOLS": ["Pr. CHEMAOU", "Pr. IDRISSI"],
    "METRE": ["Pr. JAWADI", "Pr. TOUATI"],
    "DAO (AUTOCAD)": ["Pr. ROUSSAFI"],
    "TOPOGRAPHIE": ["Pr. MESKINE", "Pr. TAZI"],
    "CALCUL DE STRUCTURE": ["Pr. JOUDA"],
}

DAYS = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI"]
SATURDAY = "SAMEDI"
EXAM_TYPES = ["Cours", "Controle", "EFM"]

# ─── الفترات الزمنية ─────────────────────────────────────────────────────────
DEFAULT_TIME_SLOTS = [
    {"start": "08:30", "end": "10:25"},
    {"start": "10:35", "end": "12:30"},
    {"start": "13:15", "end": "15:10"},
    {"start": "15:20", "end": "17:15"},
]
# ربط فترات الصباح ببعضها (0<->1) وفترات المساء ببعضها (3<->4)
SLOT_PAIR = {0: 1, 1: 0, 3: 4, 4: 3}
LEGACY_TIME_SLOT_KEYS = [
    "MATIN: 8H30 - 10H25",
    "MATIN: 10H35 - 12H30",
    "PAUSE DEJEUNER",
    "APRES-MIDI: 13H15 - 15H10",
    "APRES-MIDI: 15H20 - 17H15",
]

# ─── حسابات المستخدمين (لكل مستخدم بياناته الخاصة) ───────────────────────────
DATA_DIR = Path(__file__).parent / "user_data"
USERS_FILE = Path(__file__).parent / "users.json"
SESSIONS_FILE = Path(__file__).parent / "sessions.json"
MAX_ACCOUNTS = 3  # أقصى عدد حسابات. عند بلوغه يختفي «إنشاء حساب جديد». غيّر الرقم لو احتجت أكثر
SESSION_COOKIE = "tt_session"
SESSION_DAYS = 30  # مدة بقاء تسجيل الدخول بعد آخر دخول، حتى لو حدّثت الصفحة أو أغلقت المتصفح

# ─── التخزين القديم (قبل إضافة الحسابات) ─────────────────────────────────────
# يُستخدم فقط لترحيل البيانات القديمة تلقائياً إلى أول حساب يُنشأ — راجع
# auth._migrate_legacy_data. لا يُستخدم بعدها في أي مكان آخر بالتطبيق.
DATA_FILE = Path(__file__).parent / "saved_data.json"

# مفاتيح session_state الخاصة بخانات الجدول التفاعلي، تُستخدم لتفريغها عند
# تبديل الصفحة أو تحميل إعدادات جديدة.
PROFILE_KEY_PREFIXES = ("c_", "t_", "e_", "m_", "mg_", "r_", "link_", "config_")

# ─── رأس ملف PDF ─────────────────────────────────────────────────────────────
PDF_TITLE_BASE = "EMPLOI DU TEMPS TECHNICIENS SPECIALISES GENIE CIVIL"
DEFAULT_PDF_LEFT_HEADER = (
    "ROYAUME DU MAROC\n"
    "MINISTERE DE L'INTERIEUR\n"
    "DIRECTION DU DEVELOPPEMENT DES COMPETENCES\n"
    "ET DE LA TRANSFORMATION DIGITALE\n"
    "I.F.T.T.S CASA"
)

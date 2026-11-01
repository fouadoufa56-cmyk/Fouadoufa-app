"""
يصنع ملف users.json لحساباتك الثابتة (3 افتراضياً)، لترفعه بعدها إلى GitHub.

الاستعمال (على جهازك، داخل مجلد المشروع):

    python make_users.py

سيسألك عن اسم كل مستخدم وكلمة مروره، ثم يكتب users.json (كلمات المرور تُحفظ
مشفّرة، لا نصاً صريحاً). ملاحظة: أحرف كلمة المرور **لا تظهر** وأنت تكتبها، هذا طبيعي.
"""

import getpass
import json
import secrets
from pathlib import Path

import auth
from constants import MAX_ACCOUNTS


def build_users(entries):
    """entries: قائمة (اسم، كلمة مرور) -> قاموس users.json"""
    users = {}
    for name, password in entries:
        salt = secrets.token_hex(16)
        users[name] = {"salt": salt, "hash": auth._hash_password(password, salt)}
    return users


def _ask_entries(count):
    entries, names = [], set()
    for i in range(1, count + 1):
        while True:
            name = input(f"\nاسم المستخدم {i} (3-20 حرفاً/رقماً بدون مسافات): ").strip()
            if not auth.is_valid_username(name):
                print("  ✗ اسم غير صالح، جرّب مرة ثانية.")
            elif name in names:
                print("  ✗ هذا الاسم مكرر.")
            else:
                break
        while True:
            password = getpass.getpass("  كلمة المرور (6 أحرف على الأقل): ")
            if len(password) < auth.MIN_PASSWORD_LENGTH:
                print("  ✗ قصيرة جداً.")
            elif password != getpass.getpass("  أعدها للتأكيد: "):
                print("  ✗ غير متطابقتين.")
            else:
                break
        names.add(name)
        entries.append((name, password))
    return entries


def main(out_path=None):
    out = Path(out_path) if out_path else Path(__file__).parent / "users.json"
    raw = input(f"كم حساباً تريد؟ [{MAX_ACCOUNTS}]: ").strip()
    count = int(raw) if raw.isdigit() and int(raw) > 0 else MAX_ACCOUNTS
    if out.exists() and input(f"{out.name} موجود وسيُستبدل. متأكد؟ (y/n): ").lower() != "y":
        print("أُلغي. لم يتغيّر شيء.")
        return
    users = build_users(_ask_entries(count))
    out.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ تم إنشاء {out.name} بـ {len(users)} حسابات: {', '.join(users)}")
    print("الآن ارفعه إلى GitHub (راجع الخطوات في README).")


if __name__ == "__main__":
    main()

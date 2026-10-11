"""
بناء مفاتيح ``st.session_state`` في مكان واحد فقط.

كل خانة في الجدول لها قوائم (مادة، أستاذ، قاعة، نوع...) ولكل قائمة مفتاح
خاص بها. بتجميع بناء المفاتيح هنا، يستحيل أن يختلف الترتيب بين مكان الكتابة
ومكان القراءة (خطأ صامت يصعب اكتشافه).

الرموز: g = رمز القسم، di = رقم اليوم، si = رقم الفترة.
"""


def course_key(g: str, di: int, si: int) -> str:
    return f"c_{g}_{di}_{si}"


def teacher_key(g: str, di: int, si: int, course: str) -> str:
    return f"t_{g}_{di}_{si}_{course}"


def exam_type_key(g: str, di: int, si: int) -> str:
    return f"e_{g}_{di}_{si}"


def merge_key(g: str, di: int, si: int) -> str:
    return f"m_{g}_{di}_{si}"


def room_key(g: str, di: int, si: int) -> str:
    return f"r_{g}_{di}_{si}"


def link_key(g: str, di: int, si: int) -> str:
    return f"link_{g}_{di}_{si}"

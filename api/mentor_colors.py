"""导师配色的唯一后端入口。

色板与哈希算法与前端共用同一份数据源 ``shared/mentor-colors.json``：

- 网页标签底色取 ``light`` 变体，Word/Excel 导出字体色取 ``dark`` 变体；
- 两端都以 ``js_hash(导师姓名) % len(palette)`` 取槽位，同一导师在两处恒定同色；
- 模块不内联任何色值，改配色只需改那个 JSON。

色值一律不带 ``#`` 前缀（openpyxl 与 python-docx 的入参格式）。
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

SHARED_RELATIVE_PATH = Path('shared') / 'mentor-colors.json'


def shared_path():
    """开发态取仓库根目录；PyInstaller 冻结态取解包目录（spec 中已声明该数据文件）。"""
    root = getattr(sys, '_MEIPASS', None)
    base = Path(root) if root else Path(__file__).resolve().parents[1]
    return base / SHARED_RELATIVE_PATH


@lru_cache(maxsize=1)
def load_color_source():
    path = shared_path()
    if not path.is_file():
        raise FileNotFoundError(f'导师配色数据源缺失：{path}')
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def palette():
    return load_color_source()['palette']


def js_hash(text):
    """复刻前端 hashString：每步 hash = hash * 31 + 码位，并按 32 位有符号整数截断。

    前端的 ``hash |= 0`` 等价于本函数的截断逻辑；中文姓名都是 BMP 字符，
    Python 的逐码位迭代与 JS 的逐 UTF-16 码元迭代结果一致。
    """
    value = 0
    for char in text:
        value = (value * 31 + ord(char)) & 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return abs(value)


def color_index(name):
    """返回导师在色板中的槽位；空姓名与前端一致地落到 'unknown'。"""
    entries = palette()
    return js_hash((name or '').strip() or 'unknown') % len(entries)


def mentor_color(name):
    """导出用深色（RRGGBB），可直接传给 Font(color=...) / RGBColor.from_string()。"""
    return palette()[color_index(name)]['dark']


def build_mentor_color_map(groups):
    """收集本场确有学生参加的导师及其导出用色（导师姓名 → RRGGBB）。

    颜色本身只由姓名决定，此处的集合过滤才是重点：只有真的有学生参赛的导师才着色，
    避免无关专家被上色而稀释「师生配对」这一视觉含义。
    调用方需 prefetch groups 的 students，否则会逐组查询。
    """
    mentors = set()
    for group in groups:
        for student in group.students.all():
            mentor = (student.mentor_name or '').strip()
            if mentor:
                mentors.add(mentor)
    return {mentor: mentor_color(mentor) for mentor in sorted(mentors)}

"""导师配色的唯一后端入口。

色板与哈希算法与前端共用同一份数据源 ``shared/mentor-colors.json``：

- 网页标签底色取 ``light`` 变体，Word/Excel 导出字体色取 ``dark`` 变体；
- 两端按整份排期的导师集合排序，以哈希槽位为起点避让冲突，超出色板时扩展；
- 模块不内联任何色值，改配色只需改那个 JSON。

色值一律不带 ``#`` 前缀（openpyxl 与 python-docx 的入参格式）。
"""
import json
import sys
from functools import lru_cache
from math import gcd
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

    前端的 ``hash |= 0`` 等价于本函数的截断逻辑；按 UTF-16 码元处理，
    包含扩展汉字或表情的姓名也与 JavaScript 一致。
    """
    value = 0
    encoded = text.encode('utf-16-be', errors='surrogatepass')
    for index in range(0, len(encoded), 2):
        unit = (encoded[index] << 8) | encoded[index + 1]
        value = (value * 31 + unit) & 0xFFFFFFFF
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


def color_pair(slot):
    """Shared integer-only extension, with distinct readable light/dark pairs."""
    entries = palette()
    if slot < len(entries):
        return entries[slot]
    offset = slot - len(entries)
    if offset >= 56 ** 3:
        raise ValueError('导师数量超出可分配的独立颜色范围')
    value = (offset * 4051 + 7919) % (56 ** 3)
    channels = [value % 56, (value // 56) % 56, value // (56 ** 2)]
    return {
        'light': ''.join(f'{200 + channel:02X}' for channel in channels),
        'dark': ''.join(f'{24 + channel * 2:02X}' for channel in channels),
    }


def build_mentor_color_pairs(names):
    """Stable per-version assignment; input order and UI filters cannot change it.

    UTF-16 sorting and integer arithmetic deliberately match src/utils/color.ts.
    Preserve each preferred legacy slot unless another mentor already uses it.
    """
    names = sorted({name.strip() for name in names if name and name.strip()},
                   key=lambda name: name.encode('utf-16-be', errors='surrogatepass'))
    colors, used_slots, used_light, used_dark = {}, set(), set(), set()
    overflow = len(palette())
    step = int(load_color_source().get('collisionStep', 17))
    while gcd(step, len(palette())) != 1:
        step += 1
    for name in names:
        preferred = color_index(name)
        slot = next((candidate for offset in range(len(palette()))
                     if (candidate := (preferred + offset * step) % len(palette())) not in used_slots), None)
        if slot is None:
            slot = overflow
            pair = color_pair(slot)
            while pair['light'] in used_light or pair['dark'] in used_dark:
                slot += 1
                pair = color_pair(slot)
            overflow = slot + 1
        else:
            pair = color_pair(slot)
        used_slots.add(slot)
        used_light.add(pair['light'])
        used_dark.add(pair['dark'])
        colors[name] = pair
    return colors


def build_mentor_color_map(groups):
    """收集本场确有学生参加的导师及其导出用色（导师姓名 → RRGGBB）。

    使用该版本的完整导师集合避让重色，只有真的有学生参赛的导师才着色，
    避免无关专家被上色而稀释「师生配对」这一视觉含义。
    调用方需 prefetch groups 的 students，否则会逐组查询。
    """
    mentors = set()
    for group in groups:
        for student in group.students.all():
            mentor = (student.mentor_name or '').strip()
            if mentor:
                mentors.add(mentor)
    return {mentor: pair['dark'] for mentor, pair in build_mentor_color_pairs(mentors).items()}

"""导师配色的唯一后端入口。

色板与哈希算法与前端共用同一份数据源 ``shared/mentor-colors.json``：

- 网页标签底色取 ``light`` 变体，Word/Excel 导出字体色取 ``dark`` 变体；
- 完整排期按同组关系为教师分色，旧单姓名接口保留哈希兼容；
- 模块不内联任何色值，改配色只需改那个 JSON。

色值一律不带 ``#`` 前缀（openpyxl 与 python-docx 的入参格式）。
"""
import json
import math
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

    组内教师优先使用差异明显的颜色，同一排期跨组一致；只有真的有学生参赛的导师才着色，
    避免无关专家被上色而稀释「师生配对」这一视觉含义。
    调用方需 prefetch groups 的 students，否则会逐组查询。
    """
    mentors = set()
    graph = {}
    for group in groups:
        names = set()
        for student in group.students.all():
            mentor = (student.mentor_name or '').strip()
            if mentor:
                mentors.add(mentor)
                names.add(mentor)
        chair = getattr(group, 'chair', None)
        if chair and getattr(chair, 'name', ''):
            names.add(chair.name.strip())
        experts = getattr(group, 'experts', None)
        if experts:
            names.update(t.name.strip() for t in experts.all() if t.name.strip())
        for name in names:
            graph.setdefault(name, set()).update(names - {name})
    colors = distinct_mentor_indexes(graph)
    entries = load_color_source()['distinctPalette']
    return {mentor: entries[colors[mentor]]['dark'] for mentor in sorted(mentors)}


def _lab(hex_color):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    def f(v):
        return math.cbrt(v) if v > .008856 else 7.787 * v + 16 / 116
    x = f((.4124564 * r + .3575761 * g + .1804375 * b) / .95047)
    y = f(.2126729 * r + .7151522 * g + .072175 * b)
    z = f((.0193339 * r + .119192 * g + .9503041 * b) / 1.08883)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def distinct_mentor_indexes(graph):
    """Same version-wide DSATUR ordering and color-distance rule as the UI."""
    entries = load_color_source()['distinctPalette']
    labs = [_lab(p['light']) for p in entries]
    assigned = {}
    def distance(a, b):
        return math.sqrt(sum((v - labs[b][i]) ** 2 for i, v in enumerate(labs[a])))
    while len(assigned) < len(graph):
        pending = [name for name in graph if name not in assigned]
        name = min(pending, key=lambda n: (-len({assigned[t] for t in graph[n] if t in assigned}),
                                           -len(graph[n]), n.encode('utf-16-be')))
        neighbors = [assigned[t] for t in graph[name] if t in assigned]
        options = [i for i in range(len(entries)) if i not in neighbors] or list(range(len(entries)))
        assigned[name] = min(options, key=lambda i: (-min((distance(i, other) for other in neighbors), default=0), i))
    return assigned

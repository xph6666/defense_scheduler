"""周期性时间描述解析。

真实名册里教师不可用时间、教室可用时间常写成"周一至周五全天""每周三下午"
"周末 09:00-12:00"这类周期性中文描述，而排期算法只认
"YYYY-MM-DD HH:MM-HH:MM" 的绝对区间。本模块负责把周期性写法结合本次排期的
日期范围展开成绝对区间，供 parse_time_entries 兜底调用。
"""

import re
from datetime import date, timedelta

# "上午/下午/全天/晚上"展开成具体时刻的边界（业务口径确认：全天不含晚上）
PERIOD_CLOCK_RANGES = {
    '全天': ('08:00', '18:00'),
    '上午': ('08:00', '12:00'),
    '下午': ('14:00', '18:00'),
    '晚上': ('18:00', '22:00'),
}

# 这些写法表示"没有时间限制"，展开为零条约束：
# 教师不可用时间 → 无不可用限制；教室可用时间 → 视为全时段可用
NO_LIMIT_WORDS = {'随时', '不限', '无', '无限制', '均可', '任意', '都可以', '随时可用', '全部可用'}

WEEKDAY_INDEX = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}

# 防御：日期范围异常大时限制展开天数，避免生成海量区间
MAX_EXPAND_DAYS = 366

# "9:00-12:00" 之类的具体时刻区间（小时允许不补零）
_CLOCK_RANGE_RE = re.compile(r'([01]?\d|2[0-3]):([0-5]\d)-([01]?\d|2[0-3]):([0-5]\d)')
# "周一至周五" / "周一到周五" / "周一-周五"（"周"在"至/到/-"后可省略）
_WEEK_SPAN_RE = re.compile(r'周([一二三四五六日天])[至到\-]周?([一二三四五六日天])')
_WEEK_SINGLE_RE = re.compile(r'周([一二三四五六日天])')


_FULLWIDTH_TRANS = str.maketrans('０１２３４５６７８９', '0123456789')


def _normalize(entry):
    """统一写法：去空白、全角数字/符号转半角、星期/礼拜/每周统一为"周"。"""
    text = str(entry).translate(_FULLWIDTH_TRANS)
    for src, dst in (
        ('：', ':'), ('—', '-'), ('～', '-'), ('~', '-'),
        ('星期', '周'), ('礼拜', '周'), ('每周', '周'),
    ):
        text = text.replace(src, dst)
    return re.sub(r'\s+', '', text)


def _extract_weekdays(text):
    """提取文本中的星期集合（0=周一 … 6=周日），无星期指示时返回空集合。"""
    weekdays = set()
    if '周末' in text:
        weekdays.update({5, 6})
    if '工作日' in text:
        weekdays.update({0, 1, 2, 3, 4})
    if '每天' in text or '每日' in text:
        weekdays.update(range(7))
    for start_char, end_char in _WEEK_SPAN_RE.findall(text):
        start_idx, end_idx = WEEKDAY_INDEX[start_char], WEEKDAY_INDEX[end_char]
        if start_idx <= end_idx:
            weekdays.update(range(start_idx, end_idx + 1))
        else:
            # "周六至周一"这类跨周写法：环绕展开
            weekdays.update(range(start_idx, 7))
            weekdays.update(range(0, end_idx + 1))
    # "周末"中的"末"不在星期字表内，单字正则不会误抓；
    # 区间两端会被重复抓取，但并入集合后结果一致
    for char in _WEEK_SINGLE_RE.findall(text):
        weekdays.add(WEEKDAY_INDEX[char])
    return weekdays


def _extract_clock_ranges(text):
    """提取时刻区间：优先取具体时刻，再取"全天/上午/下午/晚上"，都没有则默认全天。"""
    ranges = []
    for h1, m1, h2, m2 in _CLOCK_RANGE_RE.findall(text):
        ranges.append((f'{int(h1):02d}:{m1}', f'{int(h2):02d}:{m2}'))
    for word, clock_range in PERIOD_CLOCK_RANGES.items():
        if word in text and clock_range not in ranges:
            ranges.append(clock_range)
    if not ranges:
        ranges.append(PERIOD_CLOCK_RANGES['全天'])
    # 起点不早于终点的区间无效，直接剔除（如误写 18:00-08:00）
    return [item for item in ranges if item[0] < item[1]]


def is_no_limit_entry(entry):
    """判断一条时间描述是否属于"随时/不限"等无限制写法。"""
    return _normalize(entry) in NO_LIMIT_WORDS


def expand_recurring_entry(entry, start_date, end_date):
    """把一条周期性时间描述展开为日期范围内的绝对区间列表。

    返回值：
    - None：不是可识别的周期性写法（调用方按原有流程报"无法识别"）
    - []：无时间限制（"随时"等），或范围内没有匹配日期
    - ['2026-04-13 08:00-18:00', ...]：展开后的绝对区间
    """
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return None
    text = _normalize(entry)
    if not text:
        return None
    if text in NO_LIMIT_WORDS:
        return []

    weekdays = _extract_weekdays(text)
    if not weekdays:
        return None
    clock_ranges = _extract_clock_ranges(text)
    if not clock_ranges:
        return None

    results = []
    current = start_date
    steps = 0
    while current <= end_date and steps < MAX_EXPAND_DAYS:
        if current.weekday() in weekdays:
            for start_clock, end_clock in clock_ranges:
                results.append(f'{current.isoformat()} {start_clock}-{end_clock}')
        current += timedelta(days=1)
        steps += 1
    return results

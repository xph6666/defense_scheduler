"""课表导入解析：把真实课表转换为教师不可用时间条目。

支持两种真实格式：
1. 矩阵式（软件学院课表）：行=节次、列=星期×周次（1-8周/9-16周），
   单元格如 "【5-12】\n宋永红"、"[9-16]\n金莉"、"9-16\n史金钢 【9-16】\n王晨旭"。
   合并单元格只有左上格有值，节次两两连堂，因此按"节次对"拼接同列文本再解析，
   可同时解决合并单元格与教师名溢出到下一行的问题。
2. 行式（学部课表）：每行一门课，"时间地点"列如
   "创新港校区-5-6043周次:第9-16周 连续周 星期三 上3,上4,下7,下8"，
   可含多个"星期X 节次列表"段。

输出条目格式与教师"不可用时间"手工录入口径一致："YYYY-MM-DD HH:MM-HH:MM"。
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# 节次对 → 上课时间段（与教室借用"第X节-第X节"口径共用）
CLASS_PERIOD_TIME_RANGES = {
    (1, 2): '08:00-10:00',
    (1, 4): '08:00-12:00',
    (3, 4): '10:00-12:00',
    (5, 6): '14:00-16:00',
    (5, 8): '14:00-18:00',
    (7, 8): '16:00-18:00',
    (9, 10): '19:00-21:00',
    (9, 11): '19:00-22:00',
    (9, 12): '19:00-22:00',
}

# 单节起止时间，用于兜底组合非常规节次对
SINGLE_PERIOD_TIMES = {
    1: ('08:00', '09:00'), 2: ('09:00', '10:00'),
    3: ('10:00', '11:00'), 4: ('11:00', '12:00'),
    5: ('14:00', '15:00'), 6: ('15:00', '16:00'),
    7: ('16:00', '17:00'), 8: ('17:00', '18:00'),
    9: ('19:00', '20:00'), 10: ('20:00', '21:00'),
    11: ('21:00', '22:00'), 12: ('21:00', '22:00'),
}

WEEKDAY_NAMES = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7}

# 周次标记：兼容全角/半角括号、无括号、带"周"字，如 【5-12】、[9-16]、9-16、【1-16周】
WEEK_RANGE_RE = re.compile(r'[【\[]?\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*周?\s*[】\]]?')
CHINESE_NAME_RE = re.compile(r'^[一-龥·]{2,4}$')


class TimetableParseError(ValueError):
    """课表格式无法识别时抛出，附带中文提示。"""


@dataclass
class ClassSession:
    """一段周期性上课占用：某教师在第 week_start~week_end 周的每周 weekday 上 period_start~period_end 节。"""
    teacher_names: List[str]
    week_start: int
    week_end: int
    weekday: int  # 1=周一 ... 7=周日
    period_start: int
    period_end: int
    week_parity: Optional[int] = None  # None=连续周, 1=单周, 0=双周


def period_pair_time(start: int, end: int) -> Optional[str]:
    """节次对映射为时间段；非常规组合用单节时间表兜底拼接。"""
    known = CLASS_PERIOD_TIME_RANGES.get((start, end))
    if known:
        return known
    if start not in SINGLE_PERIOD_TIMES or end not in SINGLE_PERIOD_TIMES:
        return None
    return f'{SINGLE_PERIOD_TIMES[start][0]}-{SINGLE_PERIOD_TIMES[end][1]}'


def _cell_text(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).replace('\xa0', ' ').strip()
    return '' if text.lower() == 'nan' else text


def _extract_names(text: str, warnings: List[str]) -> List[str]:
    """从课程块的剩余文本中切出候选教师姓名 token（合法性判定延迟到统一 resolve）。"""
    names = []
    for token in re.split(r'[\s,，、;；/]+', text):
        token = token.strip()
        if token and token not in names:
            names.append(token)
    return names


def _segment_by_known(token: str, known_names: Set[str]) -> Optional[List[str]]:
    """把无分隔符连写的多个姓名按已知姓名集合贪心切分，如 "郑帅祝继华" -> ["郑帅", "祝继华"]。"""
    if not token:
        return []
    candidates = sorted((name for name in known_names if token.startswith(name)), key=len, reverse=True)
    for name in candidates:
        rest = _segment_by_known(token[len(name):], known_names)
        if rest is not None:
            return [name] + rest
    return None


def _resolve_session_names(
    sessions: Sequence['ClassSession'],
    extra_known_names: Optional[Sequence[str]],
    warnings: List[str],
) -> None:
    """统一解析各 session 的姓名 token：合法姓名直接保留，连写 token 用已知姓名切分。"""
    known: Set[str] = {name for name in (extra_known_names or []) if name}
    for session in sessions:
        for token in session.teacher_names:
            if CHINESE_NAME_RE.match(token):
                known.add(token)

    for session in sessions:
        resolved: List[str] = []
        for token in session.teacher_names:
            if CHINESE_NAME_RE.match(token):
                if token not in resolved:
                    resolved.append(token)
                continue
            segments = _segment_by_known(token, known)
            if segments:
                for name in segments:
                    if name not in resolved:
                        resolved.append(name)
            else:
                warnings.append(f'忽略无法识别为教师姓名的内容：{token[:20]}')
        session.teacher_names = resolved


def split_course_blocks(text: str, warnings: List[str]) -> List[Tuple[Optional[Tuple[int, int]], List[str]]]:
    """把单元格文本按周次标记切成课程块，返回 [(周次范围或 None, 教师名列表)]。

    第一个周次标记之前若已有姓名（少数格子省略周次），归入周次为 None 的块，
    由调用方回填该列的默认周次。
    """
    blocks: List[Tuple[Optional[Tuple[int, int]], List[str]]] = []
    matches = list(WEEK_RANGE_RE.finditer(text))
    if not matches:
        names = _extract_names(text, warnings)
        return [(None, names)] if names else []

    head = text[:matches[0].start()]
    head_names = _extract_names(head, warnings)
    if head_names:
        blocks.append((None, head_names))

    for index, match in enumerate(matches):
        week_start, week_end = int(match.group(1)), int(match.group(2))
        if week_start > week_end:
            week_start, week_end = week_end, week_start
        tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        names = _extract_names(text[match.end():tail_end], warnings)
        if names:
            blocks.append(((week_start, week_end), names))
    return blocks


def _find_matrix_layout(grid: Sequence[Sequence[Any]]):
    """定位矩阵课表的星期行与周次行，返回 (星期行号, {列: (星期, 默认周次)})。"""
    for row_index, row in enumerate(grid[:6]):
        weekday_starts = []
        for col_index, value in enumerate(row):
            text = _cell_text(value)
            match = re.match(r'^星期([一二三四五六日天])$', text)
            if match:
                weekday_starts.append((col_index, WEEKDAY_NAMES[match.group(1)]))
        if len(weekday_starts) < 2:
            continue

        week_row = grid[row_index + 1] if row_index + 1 < len(grid) else []
        column_map: Dict[int, Tuple[int, Optional[Tuple[int, int]]]] = {}
        for pos, (start_col, weekday) in enumerate(weekday_starts):
            end_col = weekday_starts[pos + 1][0] if pos + 1 < len(weekday_starts) else len(row)
            for col in range(start_col, end_col):
                default_weeks = None
                if col < len(week_row):
                    week_match = WEEK_RANGE_RE.search(_cell_text(week_row[col]))
                    if week_match:
                        default_weeks = (int(week_match.group(1)), int(week_match.group(2)))
                column_map[col] = (weekday, default_weeks)
        return row_index, column_map
    return None, {}


def parse_matrix_grid(grid: Sequence[Sequence[Any]], warnings: List[str]) -> List[ClassSession]:
    """解析矩阵式课表网格（pandas header=None 读入的原始二维值）。"""
    weekday_row_index, column_map = _find_matrix_layout(grid)
    if weekday_row_index is None:
        raise TimetableParseError('未识别到矩阵课表的星期表头行')

    # 收集节次行：行首前 3 列中匹配 "N节"
    period_rows: List[Tuple[int, int]] = []
    for row_index in range(weekday_row_index + 2, len(grid)):
        for col in range(min(3, len(grid[row_index]))):
            match = re.match(r'^(\d{1,2})\s*节$', _cell_text(grid[row_index][col]))
            if match:
                period_rows.append((int(match.group(1)), row_index))
                break
    if not period_rows:
        raise TimetableParseError('未识别到矩阵课表的节次行')
    period_rows.sort()
    period_of_row = dict((row, period) for period, row in period_rows)

    # 节次分组：白天两两连堂配对；第 9 节起的晚间行合并为一组（合并单元格常跨 9-11 节）
    groups: List[Tuple[int, int, List[int]]] = []
    day_periods = [(p, r) for p, r in period_rows if p < 9]
    evening_periods = [(p, r) for p, r in period_rows if p >= 9]
    used: Set[int] = set()
    for period, row in day_periods:
        if period in used:
            continue
        partner = next((r for p, r in day_periods if p == period + 1), None)
        if period % 2 == 1 and partner is not None:
            groups.append((period, period + 1, [row, partner]))
            used.update({period, period + 1})
        else:
            groups.append((period, period, [row]))
            used.add(period)
    if evening_periods:
        groups.append((
            evening_periods[0][0],
            evening_periods[-1][0],
            [row for _, row in evening_periods],
        ))

    sessions: List[ClassSession] = []
    for period_start, period_end, row_indexes in groups:
        for col, (weekday, default_weeks) in column_map.items():
            texts = []
            for row_index in row_indexes:
                if col < len(grid[row_index]):
                    text = _cell_text(grid[row_index][col])
                    if text:
                        texts.append(text)
            if not texts:
                continue
            for weeks, names in split_course_blocks('\n'.join(texts), warnings):
                weeks = weeks or default_weeks
                if not weeks:
                    warnings.append(f'第{period_start}-{period_end}节的课程块缺少周次且列无默认周次，已跳过：{names}')
                    continue
                sessions.append(ClassSession(
                    teacher_names=names,
                    week_start=weeks[0],
                    week_end=weeks[1],
                    weekday=weekday,
                    period_start=period_start,
                    period_end=period_end,
                ))
    return sessions


def _split_period_runs(periods: Sequence[int]) -> List[Tuple[int, int]]:
    """把节次列表切成连续段：[3,4,7,8] -> [(3,4),(7,8)]"""
    runs = []
    for period in sorted(set(periods)):
        if runs and period == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], period)
        else:
            runs.append((period, period))
    return runs


def parse_time_location_text(text: str) -> List[Tuple[Tuple[int, int], Optional[int], int, Tuple[int, int]]]:
    """解析行式课表"时间地点"文本，返回 [(周次, 单双周, 星期, 节次段)]。"""
    results = []
    week_match = re.search(r'第?(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*周', text)
    if week_match:
        weeks = (int(week_match.group(1)), int(week_match.group(2)))
    else:
        single = re.search(r'第(\d{1,2})周', text)
        if not single:
            return []
        weeks = (int(single.group(1)), int(single.group(1)))

    parity = None
    if '单周' in text:
        parity = 1
    elif '双周' in text:
        parity = 0

    segments = re.split(r'(星期[一二三四五六日天])', text)
    for index in range(1, len(segments), 2):
        weekday = WEEKDAY_NAMES[segments[index][-1]]
        periods = [int(p) for p in re.findall(r'[上下晚]\s*(\d{1,2})', segments[index + 1])]
        for run in _split_period_runs(periods):
            results.append((weeks, parity, weekday, run))
    return results


def parse_roster_grid(grid: Sequence[Sequence[Any]], warnings: List[str]) -> List[ClassSession]:
    """解析行式课表网格：首行为表头，需含"主讲教师"与"时间地点"列。"""
    header_index = None
    teacher_col = time_col = None
    for row_index, row in enumerate(grid[:5]):
        texts = [_cell_text(value) for value in row]
        if '主讲教师' in texts and '时间地点' in texts:
            header_index = row_index
            teacher_col = texts.index('主讲教师')
            time_col = texts.index('时间地点')
            break
    if header_index is None:
        raise TimetableParseError('未识别到行式课表的"主讲教师/时间地点"表头')

    sessions: List[ClassSession] = []
    for row in grid[header_index + 1:]:
        if teacher_col >= len(row) or time_col >= len(row):
            continue
        names = _extract_names(_cell_text(row[teacher_col]), warnings)
        time_text = _cell_text(row[time_col])
        if not names or not time_text:
            continue
        for weeks, parity, weekday, (period_start, period_end) in parse_time_location_text(time_text):
            sessions.append(ClassSession(
                teacher_names=names,
                week_start=weeks[0],
                week_end=weeks[1],
                weekday=weekday,
                period_start=period_start,
                period_end=period_end,
                week_parity=parity,
            ))
    return sessions


def parse_timetable_grid(grid: Sequence[Sequence[Any]], warnings: List[str]) -> List[ClassSession]:
    """自动识别课表格式并解析。"""
    for row in grid[:5]:
        texts = [_cell_text(value) for value in row]
        if '主讲教师' in texts and '时间地点' in texts:
            return parse_roster_grid(grid, warnings)
    return parse_matrix_grid(grid, warnings)


def sessions_to_time_entries(
    sessions: Sequence[ClassSession],
    first_monday: date,
    warnings: List[str],
) -> Dict[str, Set[str]]:
    """按学期第一周周一，把周期性上课占用展开为具体日期的不可用时间条目。"""
    entries: Dict[str, Set[str]] = {}
    for session in sessions:
        time_range = period_pair_time(session.period_start, session.period_end)
        if not time_range:
            warnings.append(
                f'无法映射第{session.period_start}-{session.period_end}节的上课时间，已跳过：{session.teacher_names}'
            )
            continue
        for week in range(session.week_start, session.week_end + 1):
            if session.week_parity is not None and week % 2 != session.week_parity:
                continue
            day = first_monday + timedelta(days=(week - 1) * 7 + (session.weekday - 1))
            entry = f'{day.isoformat()} {time_range}'
            for name in session.teacher_names:
                entries.setdefault(name, set()).add(entry)
    return entries


def extract_timetable_unavailable_times(
    grid: Sequence[Sequence[Any]],
    first_monday: date,
    known_teacher_names: Optional[Sequence[str]] = None,
) -> Tuple[Dict[str, List[str]], List[str]]:
    """课表导入主入口：网格 → {教师姓名: 排序后的不可用时间条目}，附解析告警。

    known_teacher_names 传入系统已有教师姓名，用于切分课表中无分隔符连写的姓名。
    """
    warnings: List[str] = []
    sessions = parse_timetable_grid(grid, warnings)
    _resolve_session_names(sessions, known_teacher_names, warnings)
    entries = sessions_to_time_entries(sessions, first_monday, warnings)
    return {name: sorted(values) for name, values in entries.items()}, warnings

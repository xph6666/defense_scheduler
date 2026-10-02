"""Time text adapters shared by import and scheduling boundaries."""
def split_time_text(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value).replace('，', ',').replace(';', ',').replace('；', ',').replace('\n', ',')
    return [item.strip() for item in normalized.split(',') if item.strip()]


def normalize_time_text(value):
    """归一化常见时间写法：全角冒号、中文/波浪横线、斜杠日期分隔"""
    return (
        str(value)
        .replace('：', ':')
        .replace('—', '-')
        .replace('～', '-')
        .replace('~', '-')
        .replace('/', '-')
        .strip()
    )


def parse_time_entries(raw_text, date_range=None):
    """拆分并归一化时间文本，返回 (可解析条目, 无法解析的原始条目)。

    支持绝对区间（2025-05-10 09:00-12:00）；提供 date_range=(开始日, 结束日) 时，
    还支持"周一至周五全天"这类周期性写法，展开为范围内的绝对区间。
    无法解析的条目由调用方生成提示并跳过，避免一条格式错误让整次排期失败。
    """
    from algorithm import SchedulingError, parse_time_range

    from ..recurring_time import expand_recurring_entry

    valid, invalid = [], []
    for entry in split_time_text(raw_text):
        normalized = normalize_time_text(entry)
        try:
            parse_time_range(normalized)
        except SchedulingError:
            expanded = expand_recurring_entry(entry, *date_range) if date_range else None
            if expanded is None:
                invalid.append(entry)
            else:
                valid.extend(expanded)
        else:
            valid.append(normalized)
    return valid, invalid


def validate_schedule_time_text(raw_text):
    from algorithm import SchedulingError, parse_time_range

    normalized = normalize_time_text(raw_text)
    try:
        parse_time_range(normalized)
    except SchedulingError as exc:
        raise ValueError(f'时间格式无效: {raw_text}') from exc
    return normalized


def find_unrecognized_time_entries(raw_text):
    """找出既非绝对区间、也非周期性写法的时间条目，供导入时即时提醒。

    判定周期写法时不需要真实排期日期范围，用任意完整一周探测是否可识别。
    """
    from datetime import date as date_cls

    from algorithm import SchedulingError, parse_time_range

    from ..recurring_time import expand_recurring_entry

    probe_range = (date_cls(2000, 1, 3), date_cls(2000, 1, 9))
    unrecognized = []
    for entry in split_time_text(raw_text):
        try:
            parse_time_range(normalize_time_text(entry))
            continue
        except SchedulingError:
            pass
        if expand_recurring_entry(entry, *probe_range) is None:
            unrecognized.append(entry)
    return unrecognized

"""排期结果导出为学院归档的《学位论文答辩时间安排》Word 文档。

版式对齐 ``test-data/26年数据/学位论文答辩/`` 下的真实归档样例：

- 标题（黑体 15 磅居中）、副标题（仿宋_GB2312 12 磅，写明答辩日期、单元数、年级和
  人数）、注意事项，随后是两列表格：每组一个「第N组」分隔行，接着时间／地点／［主席］
  ／专家／秘书／学生；
- 表格固定列宽 1276 + 8505 缇并向左溢出正文宽度，与样例一致；
- 结构标签按样例用红色，人名按导师配色（``shared/mentor-colors.json``，与网页同一
  份数据源）：导师与其学生同色——预答辩／中期能直接看出师生配对，正式答辩（导师
  回避）时便于人工核对回避是否正确；
- 结尾是「软件学院 + 日期」。

预答辩与中期的样例不单列组长，组长排在该组专家首位；正式答辩样例单列「主席」，
所以只有正式答辩多一行。
"""
from datetime import date

from docx import Document

from . import word_forms as forms
from .mentor_colors import build_mentor_color_map
from .schedule_integrity import export_groups

# 页面与列宽取自样例：Letter 纸型、左右 3.17 厘米页边距。
PAGE = dict(width_cm=21.59, height_cm=27.94, left_cm=3.17, right_cm=3.17,
            top_cm=2.2, bottom_cm=2.2)
COLUMN_WIDTHS = (1276, 8505)
TABLE_INDENT = -714
ROW_HEIGHT = 567
BODY_SIZE = 14

# 标题、副标题前缀与注意事项是学院的固定文案，随答辩类型不同。
FORM_TEXTS = {
    'pre': {
        'title': '软件工程硕士研究生{month}学位论文预答辩时间安排',
        'period': '学位论文预答辩时间:',
        'count_students': True,
        'chair_label': None,
        'notes': ['注:本人打印4本论文（普通装订），准备好PPT.提前半小时到答辩教室！'],
    },
    'formal': {
        'title': '软件工程硕士研究生{month}学位论文正式答辩时间安排',
        'period': '学位论文正式答辩时间:',
        'count_students': True,
        'chair_label': '主席',
        'notes': ['注：本人打印6本论文（5本指定打印版、1本普通装订）、毕业登记表和评审材料、'
                  '盲审修改说明导师签字后提前提交至答辩秘书处，准备好PPT在答辩时回答专家质问、'
                  '携带纸笔记录专家的问题和建议，提前半小时到答辩教室！'],
    },
    'mid': {
        'title': '{grade}软件工程硕士研究生中期考核时间安排',
        'period': '中期考核时间段：',
        'count_students': False,
        'chair_label': None,
        'notes': ['注：1、请未缴清学费的同学，中期考核前主动缴清学费，否则成绩无法录入系统！',
                  '    2、中期考核结束：提交专家签字后的《开题报告》、《中期报告》。',
                  '    3、提前打印5-6本《开题报告》、《中期报告》（A4纸装订）、成绩单一份，'
                  '准备好PPT.提前半小时到答辩教室！'],
    },
}


def export_arrangement_document(schedule_version, defense_type=None, include_remarks=True,
                                conflicts=None, issue_date=None):
    """生成《时间安排》Word 文档对象；调用方负责写入响应。"""
    defense_type = defense_type or schedule_version.defense_type
    texts = FORM_TEXTS.get(defense_type, FORM_TEXTS['pre'])
    groups = list(export_groups(schedule_version))
    color_map = build_mentor_color_map(groups)
    slots = forms.slots_of(groups)
    grade = _grade_label(groups)
    students_total = sum(len(group.students.all()) for group in groups)

    doc = Document()
    forms.configure_document(doc, **PAGE, base_size=BODY_SIZE)

    title = forms.add_paragraph(doc, align='center', line=300)
    forms.styled_run(title, _title_text(texts, defense_type, slots, grade), font=forms.HEI,
                     size=15, color=forms.BLACK)

    subtitle = forms.add_paragraph(doc, align='center', line=300)
    forms.styled_run(subtitle, _subtitle_text(texts, slots, grade, students_total),
                     font=forms.FANG_SONG, size=12, color=forms.BLACK)

    if defense_type == 'mid':
        roster = _committee_text(groups)
        if roster:
            paragraph = forms.add_paragraph(doc, line=300)
            forms.styled_run(paragraph, f'中期考核组成员：{roster}', font=forms.FANG_SONG,
                             size=12, color=forms.BLACK)

    for note in texts['notes']:
        paragraph = forms.add_paragraph(doc, align='left', line=300)
        forms.styled_run(paragraph, note, font=forms.FANG_SONG, size=12, color=forms.BLACK)

    table = forms.build_table(doc, COLUMN_WIDTHS, indent=TABLE_INDENT, border_size=4,
                              inside_size=6, border_color=forms.BLACK)
    for index, group in enumerate(groups, start=1):
        _add_group_rows(table, index, group, texts, color_map, include_remarks)

    # 样例在表格后留三个空段再落款，纸面上给「软件学院 + 日期」留出位置。
    for _ in range(3):
        forms.add_paragraph(doc, align='center')
    signature = forms.add_paragraph(doc, align='center')
    forms.styled_run(signature, '软件学院', font=forms.FANG_SONG, size=14, bold=True)
    issued = forms.add_paragraph(doc, align='center')
    stamp = issue_date or date.today()
    forms.styled_run(issued, f'{stamp.year}年{stamp.month}月{stamp.day}日',
                     font=forms.FANG_SONG, size=14, bold=True)

    if conflicts:
        _append_conflicts(doc, conflicts)
    return doc


def export_schedule_word(schedule_version, defense_label='', include_remarks=True, conflicts=None):
    """旧入口别名：早期只导出过《时间安排》，保留以免外部脚本失效。

    ``defense_label`` 已不再使用，答辩类型以版本自身的 ``defense_type`` 为准。
    """
    return export_arrangement_document(schedule_version, schedule_version.defense_type,
                                       include_remarks, conflicts)


def _add_group_rows(table, index, group, texts, color_map, include_remarks):
    chair = getattr(group, 'chair', None)
    chair_name = chair.name if chair is not None and getattr(chair, 'name', '') else ''

    header = forms.add_row(table, height=ROW_HEIGHT)
    forms.set_cell_runs(header.cells[0], [(f'第{index}组', {'color': forms.RED})],
                        align='center', size=BODY_SIZE)
    forms.set_cell_runs(header.cells[1], [('\u3000', {})], align='left', size=BODY_SIZE)

    room_name = group.room.name if getattr(group, 'room', None) else '待定'
    rows = [('时间', [forms.arrangement_slot_text(group.time)]),
            ('地点', [f'{group.campus or ""}{room_name}'])]
    if texts['chair_label']:
        rows.append((texts['chair_label'], [chair_name or '待定']))
    rows.append(('专家', _expert_segments(group, texts, color_map)))
    rows.append(('秘书', [group.secretary.name if group.secretary else '待定']))
    rows.append(('学生', _student_segments(group, color_map, include_remarks)))

    for label, segments in rows:
        row = forms.add_row(table, height=ROW_HEIGHT)
        forms.set_cell_runs(row.cells[0], [(label, {'color': forms.RED})], align='center',
                            size=BODY_SIZE)
        forms.set_cell_runs(row.cells[1], segments, align='left', size=BODY_SIZE)


def _expert_segments(group, texts, color_map):
    """专家行：正式答辩的主席单列一行，因此不再重复；其余类型组长排在首位。"""
    chair = getattr(group, 'chair', None)
    chair_name = chair.name if chair is not None and getattr(chair, 'name', '') else ''
    names = []
    if chair_name and not texts['chair_label']:
        names.append(chair_name)
    for expert in group.experts.all():
        if expert.name and expert.name != chair_name and expert.name not in names:
            names.append(expert.name)
    return _name_segments(names, color_map) or ['待定']


def _name_segments(names, color_map):
    segments = []
    for index, name in enumerate(names):
        if index:
            segments.append(('、', {}))
        segments.append((name, {'color': color_map.get(name)}))
    return segments


def _student_segments(group, color_map, include_remarks):
    """学生行：按学号顺序只写姓名，备注按开关附在姓名后，保持样例的紧凑排版。"""
    segments = []
    for index, student in enumerate(_ordered_students(group)):
        if index:
            segments.append(('、', {}))
        mentor = (student.mentor_name or '').strip()
        segments.append((student.name, {'color': color_map.get(mentor)}))
        if include_remarks and student.remark:
            segments.append((f'（{student.remark}）', {}))
    return segments or ['待定']


def _ordered_students(group):
    """名单按学号排序，缺学号的排在后面，保证同一版本每次导出顺序一致。"""
    return sorted(group.students.all(), key=lambda item: ((item.student_no or '').strip(), item.id))


def _title_text(texts, defense_type, slots, grade):
    if defense_type == 'mid':
        return texts['title'].format(grade=f'{grade}级' if grade else '')
    days = [slot.day for slot in slots if slot.parsed]
    month = f'{min(days).year}年{min(days).month}月' if days else ''
    return texts['title'].format(month=month)


def _subtitle_text(texts, slots, grade, students_total):
    """副标题：答辩日期（共 N 个单元）+ 年级人数，样例只对学位论文答辩写人数。"""
    body = f'{texts["period"]}{forms.date_span_text(slots)}（共{len(slots)}个单元）'
    if texts.get('count_students') and students_total:
        body += f' {grade}级{students_total}人' if grade else f' 共{students_total}人'
    return body


def _grade_label(groups):
    """从学号前四位推断年级；学号不统一或不像年份时返回空串，宁可不写也不编造。"""
    prefixes = set()
    for group in groups:
        for student in group.students.all():
            number = (student.student_no or '').strip()
            if len(number) < 4 or not number[:4].isdigit():
                return ''
            prefixes.add(number[:4])
    if len(prefixes) != 1:
        return ''
    year = prefixes.pop()
    return year if 2000 <= int(year) <= 2100 else ''


def _committee_text(groups):
    """中期时间安排表要求列出全部中期考核组成员，按组顺序去重。"""
    names = []
    for group in groups:
        chair = getattr(group, 'chair', None)
        candidates = [chair] if chair is not None else []
        candidates.extend(group.experts.all())
        candidates.append(group.secretary)
        for teacher in candidates:
            name = getattr(teacher, 'name', '') if teacher is not None else ''
            if name and name not in names:
                names.append(name)
    return '、'.join(names)


def _append_conflicts(doc, conflicts):
    """把导出时的校验提示附在文档末尾，避免污染归档表格本体。"""
    heading = forms.add_paragraph(doc, align='left', page_break_before=True)
    forms.styled_run(heading, f'校验提示（共 {len(conflicts)} 项，导出前请人工复核）',
                     font=forms.HEI, size=12, color=forms.BLACK)
    for conflict in conflicts:
        paragraph = forms.add_paragraph(doc, align='left')
        color = forms.ERROR if conflict.get('level') == 'error' else forms.BLACK
        forms.styled_run(paragraph, f'{conflict.get("type") or "校验结果"}：', size=10.5,
                         bold=True, color=color)
        forms.styled_run(paragraph, conflict.get('reason') or '', size=10.5, color=color)


__all__ = ['export_arrangement_document', 'export_schedule_word', 'FORM_TEXTS', 'PAGE']

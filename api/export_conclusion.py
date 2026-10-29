"""排期结果导出为学院归档的《评审小组结论》Word 文档。

版式对齐 ``test-data/26年数据/学位论文答辩/`` 下的真实归档样例：

- 预答辩：``软件工程硕士研究生学位论文预答辩评审小组结论``，每组一页（A4）；
- 正式答辩：``软件工程硕士研究生学位论文正式答辩评审小组结论记录``，版式与预答辩
  相同，只是标题、组号写法和列宽不同；
- 中期：``研究生中期考核评审汇总表``，是另一张固定表（序号／研究生／导师／中期成绩／
  是否达到外出实习条件／备注）。

评审结论每组占一页：页头三行（学院、标题、组号）、三行大表（答辩时间与地点、学生
成绩登记区、评审结论与签名区），末尾一条灰色分隔线和学院落款。学生的姓名与导师
写在带下划线的空位上，等级用 ``A □ B+ □ B □ B- □ C □ D □`` 供专家现场勾选，因此
这些内容一律黑色——纸质表填完后不再靠颜色区分信息。
"""
from docx import Document

from . import word_forms as forms
from .schedule_integrity import export_groups

# 页边距取自样例（A4 纵向）；正式答辩与中期各用自己样例的上下边距。
PAGE = {
    'pre': dict(width_cm=21.0, height_cm=29.7, left_cm=2.5, right_cm=2.5,
                top_cm=1.37, bottom_cm=1.92),
    'formal': dict(width_cm=21.0, height_cm=29.7, left_cm=2.5, right_cm=2.5,
                   top_cm=2.4, bottom_cm=2.11),
    'mid': dict(width_cm=21.0, height_cm=29.7, left_cm=2.5, right_cm=2.5,
                top_cm=1.72, bottom_cm=0.83),
}

# 学生成绩登记区固定留出的行数：样例每页 10 行，人多时自动加行。
MIN_STUDENT_ROWS = 10
# 中期汇总表固定留出的行数，与样例一致。
MID_STUDENT_ROWS = 17
# 评审结论书写区：留 7 条手写横线（与样例一致），总高约 8.4 厘米。
WRITING_ROWS = 7
WRITING_ROW_HEIGHT = 420

FORMS = {
    'pre': {
        'title': '软件工程硕士研究生学位论文预答辩评审小组结论',
        'columns': (1080, 3920, 760, 3600),
        'conclusion_label': '学位论文预答辩小组评审结论：',
        'group_label': '（第{index}组）  .',
    },
    'formal': {
        'title': '软件工程硕士研究生学位论文正式答辩评审小组结论记录',
        'columns': (1080, 4487, 992, 2801),
        'conclusion_label': '学位论文正式答辩小组评审结论：',
        'group_label': '第{index}组 .',
    },
}

# 等级勾选区的排布（与样例 ``A □  B+ □  B □  B- □  C □ D □`` 逐 run 一致）：
# 每项为（前缀文字, 需要单独排版的符号, 符号后的空格）。
GRADE_LAYOUT = (
    ('A ', '', ''),
    ('  B', '+', ' '),
    ('  B', '', ' '),
    ('  B', '-', ' '),
    ('  C ', '', ''),
    (' D ', '', ''),
)


def export_conclusion_document(schedule_version, defense_type=None, include_remarks=True,
                               conflicts=None):
    """生成《评审小组结论》Word 文档对象；调用方负责写入响应。"""
    defense_type = defense_type or schedule_version.defense_type
    groups = list(export_groups(schedule_version))
    doc = Document()
    forms.configure_document(doc, **PAGE.get(defense_type, PAGE['pre']))
    if defense_type == 'mid':
        for index, group in enumerate(groups, start=1):
            _add_summary_page(doc, index, group, include_remarks)
    else:
        texts = FORMS.get(defense_type, FORMS['pre'])
        for index, group in enumerate(groups, start=1):
            _add_conclusion_page(doc, index, group, texts, include_remarks)
    if conflicts:
        _append_conflicts(doc, conflicts)
    return doc


# ------------------------------------------------------------ 评审小组结论 ----

def _add_conclusion_page(doc, index, group, texts, include_remarks):
    heading = forms.add_paragraph(doc, align='center', line=240, page_break_before=index > 1)
    forms.styled_run(heading, '软   件   学  院', font=forms.SONG, size=15)
    title = forms.add_paragraph(doc, align='center', line=240)
    forms.styled_run(title, texts['title'], font=forms.HEI, size=15)
    label = forms.add_paragraph(doc, align='right', line=240)
    forms.styled_run(label, texts['group_label'].format(index=index), size=9)

    table = forms.build_table(doc, texts['columns'], indent=-72)
    _add_head_row(table, group)
    _add_student_rows(table, group, include_remarks)
    _add_conclusion_area(table, texts)

    _add_college_footer(doc)
    forms.add_paragraph(doc, align='center')


def _add_head_row(table, group):
    """第一行：答辩时间（含星期与时段） + 地点。"""
    row = forms.add_row(table, height=444, cant_split=True)
    forms.set_cell_runs(row.cells[0], [('答辩时间', {})], align='center')
    forms.set_cell_runs(row.cells[1], [(forms.conclusion_slot_text(group.time), {})], align='left')
    forms.set_cell_runs(row.cells[2], [('地点', {})], align='center')
    room_name = group.room.name if getattr(group, 'room', None) else '待定'
    forms.set_cell_runs(row.cells[3],
                        [(f'{group.campus or ""}{room_name}',
                          {'font': forms.XING_KAI, 'size': 12})], align='center')


def _add_student_rows(table, group, include_remarks):
    """学生成绩登记区：每人一行，姓名与导师写在下划线空位上，等级留方框勾选。"""
    row = forms.add_row(table, height=3561, cant_split=True)
    cell = forms.collapse_cell(forms.merge_row(row, 0, 3))
    forms.format_paragraph(cell.paragraphs[0], line=240, line_rule='exact')

    students = _ordered_students(group)
    for slot in range(max(len(students), MIN_STUDENT_ROWS)):
        student = students[slot] if slot < len(students) else None
        paragraph = forms.add_paragraph(cell, line=480)
        _write_student_line(paragraph, slot + 1, student, include_remarks)


def _write_student_line(paragraph, index, student, include_remarks):
    """一行学生登记：``学生N   姓名  指导教师   导师  备注  A □ B+ □ …``。

    ``学生N`` 是 1 位还是 2 位序号会让整行左移一格，所以下划线宽度按标签宽度反算，
    保证「姓名」「指导教师」两列在整页里纵向对齐（学院样例也是这么对齐的）。
    """
    label = f'学生{index}'
    name_field = max(4, 16 - forms.wide_len(label) - 5)
    name = student.name if student is not None else ''
    mentor = (student.mentor_name or '').strip() if student is not None else ''
    forms.styled_run(paragraph, label)
    forms.styled_run(paragraph, f'   {forms.pad_wide(name, name_field)}  ', underline=True)
    forms.styled_run(paragraph, '指导教师')
    forms.styled_run(paragraph, f'   {forms.pad_wide(mentor, 6)}  ', underline=True)
    forms.styled_run(paragraph, '备注')
    forms.styled_run(paragraph, '  ')
    if student is not None and include_remarks and student.remark:
        forms.styled_run(paragraph, student.remark, size=9)
        forms.styled_run(paragraph, '  ', size=12)
    _write_grade_boxes(paragraph)


def _write_grade_boxes(paragraph):
    """等级勾选框：B+ 的加号是上标，B- 的减号与 B 同字号。"""
    for prefix, symbol, gap in GRADE_LAYOUT:
        forms.styled_run(paragraph, prefix, size=12)
        if symbol == '+':
            forms.styled_run(paragraph, symbol, size=18, superscript=True)
        elif symbol:
            forms.styled_run(paragraph, symbol, size=12)
        if gap:
            forms.styled_run(paragraph, gap, size=12)
        forms.styled_run(paragraph, '□', size=12)


def _add_conclusion_area(table, texts):
    """结论书写区与签名区。

    样例把这些横线画成「整行下划线空格」，但空格行在 Word／LibreOffice 里会被当成
    行尾空白丢掉，连续同边框的段落又会被合并成一条线。这里改成表格自身的行分隔线：
    每一行都是一条等距、等宽的横线，两种渲染器表现一致。
    """
    label_row = forms.add_row(table, height=520, cant_split=True)
    cell = forms.collapse_cell(forms.merge_row(label_row, 0, 3))
    headline = forms.format_paragraph(cell.paragraphs[0], line=360)
    forms.styled_run(headline, texts['conclusion_label'], bold=True)

    for _ in range(WRITING_ROWS):
        writing_row = forms.add_row(table, height=WRITING_ROW_HEIGHT, cant_split=True)
        forms.collapse_cell(forms.merge_row(writing_row, 0, 3))

    signature_row = forms.add_row(table, height=1300, cant_split=True)
    cell = forms.collapse_cell(forms.merge_row(signature_row, 0, 3))
    signature = forms.format_paragraph(cell.paragraphs[0], line=360,
                                       right_indent=42)
    forms.styled_run(signature, '     评审组专家签名：')
    forms.styled_run(signature, ' ' * 16, underline=True)
    forms.styled_run(signature, '     秘书签名：')
    forms.styled_run(signature, ' ' * 8, underline=True)

    dated = forms.add_paragraph(cell, line=300, line_rule='exact', first_line_indent=336)
    forms.styled_run(dated, '20    年    月    日')


# ------------------------------------------------------------ 中期汇总表 ----

def _add_summary_page(doc, index, group, include_remarks):
    college = forms.add_paragraph(doc, align='center', page_break_before=index > 1)
    forms.styled_run(college, '西安交通大学 软件学院', font=forms.KAI, size=14)
    title = forms.add_paragraph(doc, align='center')
    forms.styled_run(title, f'          研究生中期考核评审汇总表    （第{index}组）',
                     font=forms.HEI, size=18)
    forms.add_paragraph(doc, align='right')

    table = forms.build_table(doc, (889, 551, 583, 1666, 1701, 2587, 1383), indent=-72)
    _add_summary_head(table, group)
    _add_summary_columns(table)
    students = _ordered_students(group)
    for slot in range(max(len(students), MID_STUDENT_ROWS)):
        student = students[slot] if slot < len(students) else None
        _add_summary_student(table, slot + 1, student, include_remarks)
    forms.add_paragraph(doc, align='center')


def _add_summary_head(table, group):
    """表头：考核地点占两列、地点值占两列、考核时间一列、时间值占两列。"""
    row = forms.add_row(table, height=444)
    forms.merge_row(row, 5, 6)
    forms.merge_row(row, 2, 3)
    forms.merge_row(row, 0, 1)
    cells = forms.unique_cells(row)
    room_name = group.room.name if getattr(group, 'room', None) else '待定'
    forms.set_cell_runs(cells[0], [('考核地点', {})], align='center')
    forms.set_cell_runs(cells[1], [(f'{group.campus or ""}{room_name}', {})], align='center')
    forms.set_cell_runs(cells[2], [('考核时间', {})], align='center')
    forms.set_cell_runs(cells[3], [(forms.summary_slot_text(group.time), {})], align='center')


def _add_summary_columns(table):
    row = forms.add_row(table, height=444)
    forms.merge_row(row, 1, 2)
    cells = forms.unique_cells(row)
    for index, header in enumerate(('序号', '研究生', '导师', '中期成绩（100%）',
                                    '是否达到外出实习条件', '备 注')):
        forms.set_cell_runs(cells[index], [(header, {})], align='center')


def _add_summary_student(table, index, student, include_remarks):
    row = forms.add_row(table, height=420)
    forms.merge_row(row, 1, 2)
    cells = forms.unique_cells(row)
    name = student.name if student is not None else ''
    mentor = (student.mentor_name or '').strip() if student is not None else ''
    remark = student.remark if student is not None and include_remarks else ''
    forms.set_cell_runs(cells[0], [(str(index), {})], align='center')
    forms.set_cell_runs(cells[1], [(name, {})], align='center')
    forms.set_cell_runs(cells[2], [(mentor, {})], align='center')
    forms.set_cell_runs(cells[3], [('', {})], align='center')
    forms.set_cell_runs(cells[4], [('□是   □否', {})], align='center')
    forms.set_cell_runs(cells[5], [(remark or '', {'size': 9})], align='center')


# ---------------------------------------------------------------- 公共部分 ----

def _add_college_footer(doc):
    """灰分隔线 + 右起的学院名，作为每页收尾；分组之间靠下一段的分页符断开。"""
    footer = forms.add_paragraph(doc, align='center')
    forms.styled_run(footer, '————————————————————————', bold=True, color=forms.LIGHT_GRAY)
    forms.styled_run(footer, '                    ', bold=True, color=forms.LIGHT_GRAY)
    forms.styled_run(footer, '西安交通大学软件学院', size=7.5, color=forms.LIGHT_GRAY)


def _ordered_students(group):
    """名单按学号排序，缺学号的排在后面，保证同一版本每次导出顺序一致。"""
    return sorted(group.students.all(), key=lambda item: ((item.student_no or '').strip(), item.id))


def _append_conflicts(doc, conflicts):
    """把导出时的校验提示附在文档末尾，避免污染归档表格本体。"""
    heading = forms.add_paragraph(doc, align='left', page_break_before=True)
    forms.styled_run(heading, f'校验提示（共 {len(conflicts)} 项，导出前请人工复核）',
                     font=forms.HEI, size=12)
    for conflict in conflicts:
        paragraph = forms.add_paragraph(doc, align='left')
        color = forms.ERROR if conflict.get('level') == 'error' else forms.BLACK
        forms.styled_run(paragraph, f'{conflict.get("type") or "校验结果"}：', size=10.5,
                         bold=True, color=color)
        forms.styled_run(paragraph, conflict.get('reason') or '', size=10.5, color=color)


__all__ = ['export_conclusion_document', 'FORMS', 'PAGE']

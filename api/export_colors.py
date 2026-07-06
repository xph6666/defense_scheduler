"""导出配色：导师与其学生使用同一颜色，Word/Excel 两种导出保持一致语义。

调色板取自学院历年真实安排表（生成文档/ 样例）中使用过的颜色。
红色保留给结构标签（组号、时间、地点、角色名），不进入导师配色轮换。
"""

MENTOR_COLOR_PALETTE = [
    '00B050', '558ED5', '76923C', '0C4AA4', '7030A0', 'E46C0A',
    '31859C', '984806', 'D99594', '00B0F0', 'C00000', '92D050',
    'FFC000', '604A7B', '4BACC6', '8064A2',
]

LABEL_RED = 'FF0000'


def build_mentor_color_map(groups):
    """按组顺序为每位有学生参加本场答辩的导师分配稳定颜色（姓名 → RRGGBB）。

    调用方需 prefetch groups 的 students，避免逐组查询。
    """
    color_map = {}
    for group in groups:
        for student in group.students.all():
            mentor = (student.mentor_name or '').strip()
            if mentor and mentor not in color_map:
                color_map[mentor] = MENTOR_COLOR_PALETTE[len(color_map) % len(MENTOR_COLOR_PALETTE)]
    return color_map

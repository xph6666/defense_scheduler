from datetime import datetime, timedelta


TIME_SLOTS = ['08:30-10:30', '10:30-12:30', '14:00-16:00', '16:00-18:00']


def generate_schedule(teachers, students, rooms, rules):
    """根据基础硬约束生成排期分组。"""
    if not teachers or not students:
        return {
            'groups': [],
            'conflicts': [{'type': 'no_data', 'description': '教师或学生数据不足，无法生成排期'}],
        }

    defense_type = rules.get('defense_type', 'pre')
    filtered_students = [
        student for student in students
        if not student.get('defense_types') or defense_type in student.get('defense_types', []) or rules.get('defenseType') in student.get('defense_types', [])
    ] or students
    filtered_teachers = [
        teacher for teacher in teachers
        if not teacher.get('available_types') or defense_type in teacher.get('available_types', []) or rules.get('defenseType') in teacher.get('available_types', [])
    ] or teachers

    student_rule = rules.get('studentCount', {})
    students_per_group = int(student_rule.get('target') or 5)
    students_per_group = max(students_per_group, 1)
    num_groups = (len(filtered_students) + students_per_group - 1) // students_per_group
    leaders = [teacher for teacher in filtered_teachers if _has_role(teacher, ['组长', '主席'])] or filtered_teachers
    secretaries = [teacher for teacher in filtered_teachers if _has_role(teacher, ['秘书'])] or filtered_teachers
    expert_target = int((rules.get('expertCount') or {}).get('target') or 2)
    start_date = _parse_start_date(rules.get('start_date') or rules.get('startDate') or '2025-05-10')

    groups = []
    for index in range(num_groups):
        group_students = filtered_students[index * students_per_group:(index + 1) * students_per_group]
        room = _pick_room(rooms, group_students, index)
        chair = _pick_teacher(leaders, index, room, group_students, [])
        secretary = _pick_teacher(secretaries, index, room, group_students, [chair])
        experts = _pick_experts(filtered_teachers, expert_target, index, room, group_students, [chair, secretary])
        slot_date, time_slot = _pick_slot(start_date, index, len(rooms) or 1, rules)

        groups.append({
            'group_id': f'G{index + 1:02d}',
            'time': f'{slot_date} {time_slot}',
            'room_id': room['id'] if room else None,
            'campus': room.get('campus', '未分配') if room else '未分配',
            'chair_id': chair['id'] if chair else None,
            'expert_ids': [teacher['id'] for teacher in experts],
            'secretary_id': secretary['id'] if secretary else None,
            'student_ids': [student['id'] for student in group_students],
        })

    return {
        'groups': groups,
        'conflicts': [],
    }


def _has_role(teacher, roles):
    teacher_roles = teacher.get('roles') or []
    return any(role in teacher_roles for role in roles)


def _parse_start_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return datetime.strptime('2025-05-10', '%Y-%m-%d').date()


def _pick_slot(start_date, index, parallel_room_count, rules):
    day_offset = index // (parallel_room_count * len(TIME_SLOTS))
    slot_index = (index // parallel_room_count) % len(TIME_SLOTS)
    current_date = start_date + timedelta(days=day_offset)
    if rules.get('avoid_weekend') or rules.get('avoidWeekend'):
        while current_date.weekday() >= 5:
            current_date += timedelta(days=1)
    return current_date.isoformat(), TIME_SLOTS[slot_index]


def _pick_room(rooms, students, index):
    if not rooms:
        return None
    preferred_campus = students[0].get('campus') if students else None
    candidates = [room for room in rooms if room.get('campus') == preferred_campus] or rooms
    capacity_candidates = [room for room in candidates if int(room.get('capacity') or 0) >= len(students)] or candidates
    return capacity_candidates[index % len(capacity_candidates)]


def _pick_teacher(candidates, index, room, students, excluded):
    excluded_ids = {teacher['id'] for teacher in excluded if teacher}
    ordered = candidates[index:] + candidates[:index]
    for teacher in ordered:
        if teacher['id'] in excluded_ids:
            continue
        if _violates_mentor_avoidance(teacher, students):
            continue
        if room and teacher.get('campus_preference') and teacher.get('campus_preference') != room.get('campus'):
            continue
        return teacher
    for teacher in ordered:
        if teacher['id'] not in excluded_ids:
            return teacher
    return None


def _pick_experts(teachers, target, index, room, students, excluded):
    picked = []
    excluded_ids = {teacher['id'] for teacher in excluded if teacher}
    ordered = teachers[index:] + teachers[:index]
    for teacher in ordered:
        if len(picked) >= target:
            break
        if teacher['id'] in excluded_ids:
            continue
        if _violates_mentor_avoidance(teacher, students):
            continue
        if any(_teachers_should_avoid(teacher, other) for other in picked):
            continue
        if room and teacher.get('campus_preference') and teacher.get('campus_preference') != room.get('campus'):
            continue
        picked.append(teacher)
    if len(picked) < target:
        for teacher in ordered:
            if len(picked) >= target:
                break
            if teacher['id'] not in excluded_ids and teacher not in picked:
                picked.append(teacher)
    return picked


def _violates_mentor_avoidance(teacher, students):
    return any(student.get('mentor_name') and student.get('mentor_name') == teacher.get('name') for student in students)


def _teachers_should_avoid(left, right):
    left_names = _split_names(left.get('avoid_teacher_names', ''))
    right_names = _split_names(right.get('avoid_teacher_names', ''))
    return right.get('name') in left_names or left.get('name') in right_names


def _split_names(value):
    return [name.strip() for name in value.replace('，', ',').split(',') if name.strip()]

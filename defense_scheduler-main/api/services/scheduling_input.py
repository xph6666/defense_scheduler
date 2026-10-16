"""Convert persistent reference data into the scheduling engine contract."""
from ..models import Room, ScheduleVersion, Student, Teacher
from ..serializers import DEFENSE_TYPE_LABELS
from .time_data import parse_time_entries, split_time_text

def build_algorithm_input(defense_type, date_range=None, rules=None, *, secretary_bindings=None):
    """按答辩类型过滤参与者并转换为算法输入结构。

    过滤语义：
    - 学生 defense_types 必须包含当前答辩类型；为空视为数据缺失，跳过并生成提示。
    - 教师 available_types 为空视为不限类型；非空则必须包含当前类型。
    - 姓名→ID 映射基于过滤后的教师集合：被过滤的导师本就不会被排入，
      supervisor_id 置空即可，避免算法校验到不存在的教师 ID。

    date_range=(开始日, 结束日) 用于把"周一至周五全天"等周期性时间描述
    展开为具体日期区间。

    返回 (算法输入 dict, 数据提示列表)。
    """
    defense_label = DEFENSE_TYPE_LABELS.get(defense_type, defense_type)
    rules = rules or {}
    students = list(Student.objects.select_related('mentor', 'bound_secretary'))
    rooms = list(Room.objects.all())

    all_teachers = list(Teacher.objects.all())
    teachers = [
        teacher for teacher in all_teachers
        if teacher.is_active and (not (teacher.available_types or []) or defense_label in teacher.available_types)
    ]
    teacher_name_counts = {}
    for teacher in teachers:
        teacher_name_counts[teacher.name] = teacher_name_counts.get(teacher.name, 0) + 1
    duplicate_teacher_names = sorted(name for name, count in teacher_name_counts.items() if count > 1)
    if duplicate_teacher_names:
        raise ValueError(f'教师姓名重复，无法可靠匹配导师/秘书：{"、".join(duplicate_teacher_names)}')
    teacher_by_name = {teacher.name: teacher for teacher in teachers}
    all_teacher_by_id = {teacher.pk: teacher for teacher in all_teachers}
    # 含未参加本场答辩类型的教师，用于区分“姓名写错”与“被类型过滤”
    all_teacher_by_name = {teacher.name: teacher for teacher in all_teachers}

    data_notices = []
    unmatched_mentors = []
    filtered_mentors = []
    unmatched_secretaries = []
    filtered_secretaries = []

    teacher_payload = []
    for teacher in teachers:
        forbidden_with = [
            teacher_by_name[name].id
            for name in [item.strip() for item in teacher.avoid_teacher_names.replace('，', ',').split(',') if item.strip()]
            if name in teacher_by_name
        ]
        unavailable_times, invalid_times = parse_time_entries(teacher.unavailable_times, date_range)
        if rules.get('course_half_day_blocking'):
            unavailable_times = expand_busy_half_days(unavailable_times)
        if invalid_times:
            data_notices.append({
                'type': 'invalid_time_format',
                'description': (
                    f'教师 {teacher.name} 的不可用时间格式无法识别，该教师暂停自动分配：'
                    f'{"、".join(invalid_times)}'
                    f'（支持如 2025-05-10 09:00-12:00 或 周一至周五全天、每周三下午）'
                ),
                'related_ids': [teacher.id],
            })
        teacher_payload.append({
            'id': teacher.id,
            'name': teacher.name,
            'college': teacher.college,
            'is_external': teacher.is_external,
            'title': teacher.title,
            'roles': teacher.roles,
            'is_active': teacher.is_active,
            'member_eligible': teacher.member_eligible,
            'is_software_teacher': teacher.is_software_teacher or (not teacher.is_external and '软件' in teacher.college),
            'available_time': unavailable_times,
            'availability_invalid': bool(invalid_times),
            'campus_preference': teacher.campus_preference,
            'forbidden_with': forbidden_with,
        })

    # 正式答辩沿用预答辩分组：把预答辩当前版本的组号随学生传给算法
    previous_group_map = {}
    previous_secretary_map = {}
    if defense_type == 'formal' and rules.get('preserve_pre_defense_groups', True):
        if '_source_pre_version_id' in rules:
            previous_version = ScheduleVersion.objects.filter(pk=rules['_source_pre_version_id'], defense_type='pre').first()
        else:
            previous_version = ScheduleVersion.objects.filter(defense_type='pre', is_current=True).first()
        if previous_version:
            from ..schedule_integrity import export_groups
            for previous_group in export_groups(previous_version):
                for member in previous_group.students.all():
                    previous_group_map[member.id] = previous_group.group_id
                    previous_secretary_map[member.id] = getattr(member, 'bound_secretary_id', None) or previous_group.secretary_id

    student_payload = []
    missing_type_students = []
    for student in students:
        defense_types = student.defense_types or []
        if not defense_types:
            missing_type_students.append(student)
            continue
        if defense_label not in defense_types:
            continue

        mentor_name = (student.mentor.name if student.mentor_id else student.mentor_name or '').strip()
        refresh_secretary = defense_type == 'pre' and rules.get('refresh_secretary_bindings')
        effective_bindings = secretary_bindings if secretary_bindings is not None else previous_secretary_map
        if refresh_secretary:
            secretary_name = ''
        elif student.pk in effective_bindings:
            saved_id = effective_bindings[student.pk]
            saved_teacher = all_teacher_by_id.get(saved_id)
            secretary_name = saved_teacher.name if saved_teacher else (f'编号 {saved_id}' if saved_id else '')
        else:
            secretary_name = (student.bound_secretary.name if student.bound_secretary_id else student.secretary_name or '').strip()
        mentor = teacher_by_name.get(mentor_name) if mentor_name else None
        secretary = teacher_by_name.get(secretary_name) if secretary_name else None
        if rules.get('policy_version', 1) >= 2 and not mentor_name:
            data_notices.append({'type': 'mentor_missing',
                'description': f'学生 {student.name} 尚未设置导师，请补齐导师关系后发布',
                'related_ids': [student.pk]})

        if mentor_name and mentor is None:
            if mentor_name in all_teacher_by_name:
                filtered_mentors.append((student, mentor_name))
            else:
                unmatched_mentors.append((student, mentor_name))
        if secretary_name and secretary is None:
            if secretary_name in all_teacher_by_name:
                filtered_secretaries.append((student, secretary_name))
            else:
                unmatched_secretaries.append((student, secretary_name))

        student_payload.append({
            'id': student.id,
            'name': student.name,
            'type': student.student_type,
            'supervisor_id': mentor.id if mentor else None,
            'campus': student.campus,
            'secretary_id': secretary.id if secretary else None,
            'previous_group_id': previous_group_map.get(student.id),
        })

    if missing_type_students:
        names = '、'.join(student.name for student in missing_type_students)
        data_notices.append({
            'type': 'student_defense_type_missing',
            'description': f'以下学生未设置参加答辩类型，本次排期已跳过：{names}',
            'related_ids': [student.id for student in missing_type_students],
        })

    def _append_match_notices(items, notice_type, description_builder):
        if not items:
            return
        # 按教师姓名聚合，避免同一错误导师被多名学生重复刷屏
        by_name = {}
        for student, person_name in items:
            by_name.setdefault(person_name, []).append(student)
        for person_name, related_students in sorted(by_name.items()):
            student_names = '、'.join(s.name for s in related_students[:5])
            extra = f'等{len(related_students)}人' if len(related_students) > 5 else ''
            data_notices.append({
                'type': notice_type,
                'description': description_builder(person_name, student_names, extra, len(related_students)),
                'related_ids': [s.id for s in related_students],
                'teacher_name': person_name,
            })

    _append_match_notices(
        unmatched_mentors,
        'mentor_not_found',
        lambda person_name, student_names, extra, _count: (
            f'以下学生填写的导师“{person_name}”在教师名单中不存在，'
            f'本次排期已忽略该导师关系：{student_names}{extra}。请核对导师姓名是否与教师表完全一致'
        ),
    )
    _append_match_notices(
        filtered_mentors,
        'mentor_unavailable_for_defense',
        lambda person_name, student_names, extra, _count: (
            f'导师“{person_name}”未设置为可参加【{defense_label}】，'
            f'其学生（{student_names}{extra}）本次无法应用导师同组/回避约束。'
            f'请在教师数据中补充可参加答辩类型'
        ),
    )
    _append_match_notices(
        unmatched_secretaries,
        'secretary_not_found',
        lambda person_name, student_names, extra, _count: (
            f'以下学生绑定的秘书“{person_name}”在教师名单中不存在，'
            f'本次无法沿用该秘书：{student_names}{extra}。请核对秘书姓名'
        ),
    )
    _append_match_notices(
        filtered_secretaries,
        'secretary_unavailable_for_defense',
        lambda person_name, student_names, extra, _count: (
            f'秘书“{person_name}”未设置为可参加【{defense_label}】，'
            f'其绑定学生（{student_names}{extra}）本次无法沿用该秘书。'
            f'请在教师数据中补充可参加答辩类型'
        ),
    )

    room_payload = []
    for room in rooms:
        available_times, invalid_times = parse_time_entries(room.available_times, date_range)
        if invalid_times:
            data_notices.append({
                'type': 'invalid_time_format',
                'description': (
                    f'教室 {room.name} 的可用时间格式无法识别，该教室暂停自动分配：'
                    f'{"、".join(invalid_times)}'
                    f'（支持如 2025-05-10 09:00-12:00 或 周一至周五全天、每周三下午）'
                ),
                'related_ids': [room.id],
            })
        elif not available_times:
            from ..recurring_time import is_no_limit_entry

            room_entries = split_time_text(room.available_times)
            if room_entries and not all(is_no_limit_entry(item) for item in room_entries):
                # 例如可用时间只写了"周末全天"而排期范围全在工作日：
                # 展开为空会让算法误判为"未填=全时段可用"，这里提示用户核实
                data_notices.append({
                    'type': 'invalid_time_format',
                    'description': (
                        f'教室 {room.name} 的可用时间（{room.available_times}）'
                        f'在本次排期日期范围内没有匹配的日期，本次不使用该教室'
                    ),
                    'related_ids': [room.id],
                })
        from ..recurring_time import is_no_limit_entry
        restricted = any(not is_no_limit_entry(item) for item in split_time_text(room.available_times))
        room_payload.append({
            'id': room.id,
            'campus': room.campus,
            'name': room.name,
            'available_time': available_times,
            'capacity': room.capacity,
            'availability_restricted': restricted,
            'availability_invalid': bool(invalid_times),
        })

    return {
        'teachers': teacher_payload,
        'students': student_payload,
        'rooms': room_payload,
    }, data_notices


def expand_busy_half_days(entries):
    """A course in either half of the day reserves that complete half-day."""
    from algorithm import parse_time_range
    from datetime import datetime, timedelta
    labels = set()
    for entry in entries:
        interval = parse_time_range(entry)
        day = interval.start.date()
        while day <= interval.end.date():
            for start_hour, end_hour in ((0, 12), (12, 24)):
                start = datetime.combine(day, datetime.min.time()) + timedelta(hours=start_hour)
                end = datetime.combine(day, datetime.min.time()) + timedelta(hours=end_hour)
                if start < interval.end and interval.start < end:
                    labels.add(f'{start:%Y-%m-%d %H:%M}-{end:%Y-%m-%d %H:%M}')
            day += timedelta(days=1)
    return sorted(labels)

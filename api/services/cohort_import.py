"""Joint import of an authoritative software-college roster and student files.

Missing mentors are explicit external experts, never invented professors. The
same plan is validated again on confirmation; its preview performs no writes.
"""
import hashlib
import json

from django.utils import translation
from defense_scheduler.upload_limits import MAX_IMPORT_BATCH_SIZE
from scheduling.policies import effective_teacher_roles

from ..models import Student, Teacher
from ..serializers import TeacherSerializer, StudentSerializer
from .student_participation import nonparticipation_reason

UNKNOWN_EXTERNAL_TITLE = '外院导师（职称待确认）'
DEFENSE_TYPES = ('预答辩', '正式答辩', '中期答辩')
CAMPUSES = ('创新港', '兴庆')


def _json_option(request, key, default):
    value = request.data.get(key)
    if value in (None, ''):
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        raise ValueError(f'{key} 格式不正确，请重新检查')


def import_cohort(request):
    # Reuse the application's existing header/Excel reader without introducing
    # a module-import cycle between HTTP views and import services.
    from ..views import (TeacherViewSet, StudentViewSet, read_import_dataframe,
                         normalize_import_cell, MAX_IMPORT_FILE_SIZE, MAX_IMPORT_ROWS)

    teacher_file = request.FILES.get('teacherFile')
    student_files = request.FILES.getlist('studentFiles')
    if not teacher_file or not 1 <= len(student_files) <= 10:
        raise ValueError('请选择一份软件学院教师名单和 1～10 份学生名册')
    uploads = [teacher_file, *student_files]
    if any(item.size > MAX_IMPORT_FILE_SIZE for item in uploads):
        raise ValueError('每份文件不能超过 5 MB')
    if sum(item.size for item in uploads) > MAX_IMPORT_BATCH_SIZE:
        raise ValueError('本批文件合计不能超过 20 MB')
    types = _json_option(request, 'defenseTypes', [])
    if not isinstance(types, list) or not types or any(item not in DEFENSE_TYPES for item in types):
        raise ValueError('请选择本批学生参加的答辩环节')
    types = list(dict.fromkeys(types))
    fallback_campus = request.data.get('campus', '')
    if fallback_campus and fallback_campus not in CAMPUSES:
        raise ValueError('空白校区仅可补充为创新港或兴庆')
    corrections = _json_option(request, 'corrections', {})
    student_sheets = _json_option(request, 'studentSheets', {})
    if not isinstance(corrections, dict) or not isinstance(student_sheets, dict):
        raise ValueError('工作表或校区修正格式不正确')
    if any(not isinstance(value, dict) or set(value) != {'campus'}
           or value['campus'] not in CAMPUSES for value in corrections.values()):
        raise ValueError('逐行修正只支持明确选择创新港或兴庆')

    preview = str(request.data.get('preview', '')).lower() == 'true'
    errors, warnings, files = [], [], []

    def error(key, refs, field, message):
        errors.append({'key': key, 'sources': refs, 'errors': {field: [message]}})

    def read(upload, view, sheet, index, kind):
        if not upload.name.lower().endswith(('.xlsx', '.xls', '.csv')):
            raise ValueError('仅支持 Excel 或 CSV 文件')
        upload.seek(0)
        digest = hashlib.sha256(upload.read()).hexdigest()[:16]
        upload.seek(0)
        frame = read_import_dataframe(upload, upload.name.lower(), view._get_import_header_aliases(), sheet)
        selected = frame.attrs.get('sheet', '')
        files.append({'kind': kind, 'index': index, 'name': upload.name,
                      'sheets': frame.attrs.get('sheets', []), 'sheetName': selected})
        if len(frame) > MAX_IMPORT_ROWS:
            raise ValueError(f'{upload.name} 超过单文件 {MAX_IMPORT_ROWS} 行限制')
        required = {'name'} if kind == 'teacher' else {'name', 'studentNo', 'mentorName'}
        if not required.issubset(frame.columns):
            error('', [{'file': upload.name, 'sheet': selected}], 'file', '未识别到姓名、学号或导师等必要表头，请核对工作表')
            return []
        rows = []
        for row_index, source in frame.iterrows():
            values = {key: value for key, raw in source.items()
                      if (value := normalize_import_cell(raw)) is not None}
            row = int(row_index) + 1
            key = f'{index}:{digest}:{selected}:{row}'
            refs = [{'file': upload.name, 'sheet': selected, 'row': row}]
            rows.append((key, refs, values))
        if not rows:
            error('', [{'file': upload.name, 'sheet': selected}], 'file', '当前工作表没有资料行')
        return rows

    teacher_view, student_view = TeacherViewSet(), StudentViewSet()
    internal = {}
    for key, refs, raw in read(teacher_file, teacher_view, request.data.get('teacherSheet') or None, -1, 'teacher'):
        raw = teacher_view.prepare_import_row(raw, teacher_file.name)
        name = str(raw.get('name') or '').strip()
        if not name:
            error(key, refs, 'name', '教师姓名不能为空')
            continue
        raw['name'] = name
        if name in internal:
            if internal[name][2] != raw:
                error(key, refs, 'name', '软件学院名单存在同名且资料不一致的教师，请核对身份')
            else:
                internal[name][1].extend(refs)
            continue
        internal[name] = (key, refs, raw)

    raw_students = []
    for index, upload in enumerate(student_files):
        raw_students.extend(read(upload, student_view, student_sheets.get(str(index)) or None, index, 'student'))
    if len(raw_students) > 3000:
        raise ValueError('本批学生资料合计不能超过 3000 行')
    row_keys = {key for key, _, _ in raw_students}
    if set(corrections) - row_keys:
        raise ValueError('文件或工作表已经变化，原校区修正已失效，请重新检查')

    students = {}
    mentors = {}
    for key, refs, raw in raw_students:
        raw['defenseTypes'] = types
        raw = student_view.prepare_import_row(raw, '')
        excluded = bool(nonparticipation_reason(raw.get('remark')))
        values = {field: raw[field] for field in (
            'name', 'studentNo', 'gender', 'studentType', 'mentorName', 'campus', 'defenseTypes', 'remark') if field in raw}
        for field in ('name', 'studentNo', 'mentorName'):
            values[field] = str(values.get(field) or '').strip()
            if not values[field] and (field != 'mentorName' or not excluded):
                error(key, refs, field, {'name': '学生姓名', 'studentNo': '学号', 'mentorName': '导师姓名'}[field] + '不能为空')
        values['campus'] = str(values.get('campus') or ('' if excluded else fallback_campus)).strip()
        if key in corrections and not excluded:
            values['campus'] = corrections[key]['campus']
        if not excluded and values['campus'] not in CAMPUSES:
            error(key, refs, 'campus', '校区缺失或不明确，请在预览中选择；线上地点不能自动换算校区')
        number = values['studentNo']
        existing = Student.objects.filter(student_no=number).first() if number else None
        if existing and existing.name != values['name']:
            error(key, refs, 'studentNo', '此学号已属于其他姓名的学生，不能自动覆盖')
        if number and number in students:
            previous = students[number]
            if previous['values'] != values:
                error(key, refs, 'studentNo', '多份名册中的同一学号资料不一致，请核对后再导入')
            else:
                previous['sources'].extend(refs)
            continue
        identity = number or key
        item = {'key': key, 'sources': refs, 'values': values, 'instance': existing, 'excluded': excluded}
        students[identity] = item
        if values['mentorName'] and not excluded:
            mentors.setdefault(values['mentorName'], []).append(item)

    teachers = []
    for name in dict.fromkeys([*internal, *mentors]):
        existing = Teacher.objects.filter(name=name).first()
        is_internal = name in internal
        if is_internal:
            key, refs, raw = internal[name]
            payload = {field: raw[field] for field in (
                'name', 'college', 'title', 'roles', 'isActive', 'memberEligible',
                'unavailableTimes', 'avoidTeacherNames', 'campusPreference', 'remark')
                if raw.get(field) is not None and raw.get(field) != ''}
            for field in ('isActive', 'memberEligible'):
                if isinstance(payload.get(field), str):
                    payload[field] = payload[field].strip().lower() in ('true', '1', '是', 'yes')
            if payload.get('unavailableTimes'):
                from .time_data import parse_time_entries, find_unrecognized_time_entries
                valid_times, invalid_times = parse_time_entries(payload['unavailableTimes'])
                if find_unrecognized_time_entries(payload['unavailableTimes']):
                    error(key, refs, 'unavailableTimes', '无法识别教师不可用时间，请补齐完整日期／时段')
                payload['unavailableTimes'] = ','.join([*valid_times, *invalid_times])
            payload.setdefault('college', existing.college if existing and existing.college else '软件学院')
            payload.setdefault('title', existing.title if existing and existing.title else '职称待确认')
            payload.setdefault('roles', existing.roles if existing and existing.roles else ['普通专家'])
            payload.update(isExternal=False, isSoftwareTeacher=True, expertOnly=False)
            payload['roles'] = effective_teacher_roles({
                'roles':payload['roles'],
                'member_eligible':payload.get('memberEligible',existing.member_eligible if existing else True),
            })
        else:
            related = mentors[name]
            key, refs = related[0]['key'], [source for item in related for source in item['sources']]
            payload = {'name': name, 'college': existing.college if existing and existing.college else '外院（学院待确认）',
                       'title': existing.title if existing and existing.title else UNKNOWN_EXTERNAL_TITLE,
                       'isExternal': True, 'isSoftwareTeacher': False, 'expertOnly': True,
                       'memberEligible': True, 'roles': ['普通专家']}
        if existing and not existing.available_types:
            payload['availableTypes'] = []  # Preserve legacy "all types" semantics.
        else:
            payload['availableTypes'] = list(dict.fromkeys([*(existing.available_types if existing else []), *types]))
        if existing and not existing.is_active:
            warnings.append(f'{name} 原先已停用，本次不会自动启用，请在教师资料核对')
        serializer = TeacherSerializer(existing, data=payload, partial=bool(existing))
        with translation.override('zh-hans'):
            valid = serializer.is_valid()
        if not valid:
            errors.append({'key': key, 'sources': refs, 'errors': serializer.errors})
        current = TeacherSerializer(existing).data if existing else {}
        action = 'create' if not existing else 'update' if any(current.get(k) != v for k, v in payload.items()) else 'keep'
        teachers.append({'key': key, 'sources': refs, **payload, 'action': action,
                         'studentCount': len(mentors.get(name, [])), '_serializer': serializer})

    student_rows, excluded_rows = [], []
    for item in students.values():
        values, existing = item['values'], item['instance']
        serializer = StudentSerializer(existing, data=values, partial=bool(existing))
        with translation.override('zh-hans'):
            valid = serializer.is_valid()
        if not valid:
            errors.append({'key': item['key'], 'sources': item['sources'], 'errors': serializer.errors})
        current = StudentSerializer(existing).data if existing else {}
        action = 'create' if not existing else 'update' if any(current.get(k) != v for k, v in values.items()) else 'keep'
        target_rows = excluded_rows if item['excluded'] else student_rows
        target_rows.append({'key': item['key'], 'sources': item['sources'], **values, 'action': action,
                             'externalMentor': values['mentorName'] not in internal})

    stats = {'students': len(student_rows), 'totalStudents': len(students), 'excludedStudents': len(excluded_rows),
             'teachers': len(teachers), 'softwareTeachers': len(internal),
             'externalMentors': len(set(mentors) - set(internal)),
             'newTeachers': sum(item['action'] == 'create' for item in teachers),
             'newStudents': sum(item['action'] == 'create' for item in student_rows),
             'duplicateStudentRows': len(raw_students) - len(students)}
    if not internal or not students:
        error('', [], 'file', '教师名单及学生名册均须包含有效资料')
    # Domain checks and serializers may flag the same source field. Keep the
    # actionable domain message once, while retaining other fields on that row.
    grouped_errors = {}
    for item in errors:
        identity = item['key'] or json.dumps(item['sources'], sort_keys=True, ensure_ascii=False)
        grouped = grouped_errors.setdefault(identity, {**item, 'errors': {}})
        for field, messages in item['errors'].items():
            grouped['errors'].setdefault(field, messages)
    errors = list(grouped_errors.values())
    can_import = not errors
    if preview or not can_import:
        return {'preview': preview, 'canImport': can_import, 'stats': stats, 'files': files,
                'teachers': [{k: v for k, v in item.items() if not k.startswith('_')} for item in teachers],
                'students': student_rows, 'excludedStudents': excluded_rows, 'errors': errors, 'warnings': warnings}

    # AuditedDataMixin owns the write transaction and draft-revision guard.
    for item in teachers:
        if item['action'] != 'keep':
            item['_serializer'].save()
    for item in students.values():
        # Bind new mentors now that every validated teacher has been saved.
        serializer = StudentSerializer(item['instance'], data=item['values'], partial=bool(item['instance']))
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return {'message': f'已导入 {len(students)} 位学生资料，其中参排 {len(student_rows)} 位、不参加本次答辩 {len(excluded_rows)} 位；教师 {len(teachers)} 位',
            'stats': stats, 'warnings': warnings}

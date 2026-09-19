from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.conf import settings
from datetime import timedelta
from .authentication import login_attempt_key, check_login_attempts, record_login_failure
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Max
from .schedule_integrity import schedule_write, audit, capture_export_groups, export_groups
from django.http import HttpResponse
from django.utils import timezone, translation
import json
from datetime import datetime
from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher
from .audit import AuditedDataMixin
from .permissions import IsAdminOrReadOnly, IsAdminUser, is_admin_user
from .timetable import CLASS_PERIOD_TIME_RANGES, TimetableParseError, extract_timetable_unavailable_times
from .serializers import (
    DEFENSE_TYPE_LABELS,
    OperationLogSerializer,
    RuleConfigSerializer,
    RoomSerializer,
    ScheduleVersionSerializer,
    StudentSerializer,
    TeacherSerializer,
    default_rule_config,
)


MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1000
IMPORT_HEADER_ALIASES = {
    '姓名': 'name',
    '教师姓名': 'name',
    '学生姓名': 'name',
    '所属学院': 'college',
    '所在学院': 'college',
    '学院': 'college',
    '是否外院': 'isExternal',
    '职称': 'title',
    '可担任角色': 'roles',
    '角色': 'roles',
    '校区偏好': 'campusPreference',
    '不可用时间': 'unavailableTimes',
    '不宜同组名单': 'avoidTeacherNames',
    '学生类型': 'studentType',
    '学科': 'studentType',
    '学号': 'studentNo',
    '性别': 'gender',
    '导师姓名': 'mentorName',
    '导师': 'mentorName',
    '所属校区': 'campus',
    '校区': 'campus',
    '答辩地点': 'campus',
    '对应秘书姓名': 'secretaryName',
    '教室名称': 'name',
    '教室': 'name',
    '容量': 'capacity',
    '容纳人数': 'capacity',
    '可用时间段': 'availableTimes',
    '可用时间': 'availableTimes',
    '使用日期': 'useDate',
    '使用时间': 'useTime',
    '备注': 'remark',
}

IMPORT_KNOWN_FIELDS = {
    'id', 'name', 'college', 'isExternal', 'is_external', 'title', 'roles',
    'availableTypes', 'available_types', 'campusPreference', 'campus_preference',
    'unavailableTimes', 'unavailable_times', 'avoidTeacherNames', 'avoid_teacher_names',
    'remark', 'studentType', 'student_type', 'mentorName', 'mentor_name', 'campus',
    'studentNo', 'student_no', 'gender',
    'defenseTypes', 'defense_types', 'secretaryName', 'secretary_name', 'capacity',
    'availableTimes', 'available_times', 'useDate', 'use_date', 'useTime', 'use_time',
}


def split_time_text(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value).replace('，', ',').replace(';', ',').replace('；', ',').replace('\n', ',')
    return [item.strip() for item in normalized.split(',') if item.strip()]


def split_import_list_text(value):
    normalized = (
        str(value)
        .replace('，', ',')
        .replace('、', ',')
        .replace(';', ',')
        .replace('；', ',')
        .replace('/', ',')
        .replace('\n', ',')
    )
    return [item.strip() for item in normalized.split(',') if item.strip()]


def normalize_import_cell(value):
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str):
        value = value.replace('\xa0', ' ').strip()
        return value if value else None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return value


def normalize_import_header(value, header_aliases, index):
    text = normalize_import_cell(value)
    if text is None:
        return f'__column_{index}'
    text = str(text).strip()
    if text.startswith('Unnamed:'):
        return f'__column_{index}'
    return header_aliases.get(text, text)


def import_header_score(row, header_aliases):
    score = 0
    for index, value in enumerate(row):
        header = normalize_import_header(value, header_aliases, index)
        if header in IMPORT_KNOWN_FIELDS:
            score += 1
    return score


def read_import_dataframe(file, filename, header_aliases):
    import pandas as pd

    if filename.endswith('.csv'):
        raw = pd.read_csv(file, header=None)
    elif filename.endswith(('.xls', '.xlsx')):
        raw = pd.read_excel(file, header=None)
    else:
        raise ValueError('不支持的文件格式')

    if raw.empty:
        return raw

    scores = [import_header_score(row, header_aliases) for row in raw.values[:10]]
    header_index = max(range(len(scores)), key=lambda index: scores[index])
    if scores[header_index] == 0:
        header_index = 0

    columns = [
        normalize_import_header(value, header_aliases, index)
        for index, value in enumerate(raw.iloc[header_index].tolist())
    ]
    df = raw.iloc[header_index + 1:].copy()
    df.columns = columns
    return df.dropna(how='all')


def normalize_campus_text(value):
    if value is None:
        return value
    text = str(value).strip()
    if text.endswith('校区'):
        text = text[:-2]
    return text


def infer_defense_types_from_filename(filename):
    if '中期' in filename:
        return ['中期答辩']
    if '预答辩' in filename:
        return ['预答辩']
    if '正式' in filename or '答辩地点统计' in filename:
        return ['正式答辩']
    return []


def normalize_class_period_time(value):
    import re

    if not value:
        return ''
    text = str(value).strip()
    match = re.search(r'第\s*(\d+)\s*节\s*-\s*第?\s*(\d+)\s*节', text)
    if not match:
        return text
    start, end = int(match.group(1)), int(match.group(2))
    return CLASS_PERIOD_TIME_RANGES.get((start, end), text)


def parse_card_style_room_text(text, filename):
    import re

    match = re.search(
        r'(?P<room>\d+-\d+).*?(?P<date>\d{4}-\d{2}-\d{2})\s+'
        r'(?P<start>\d{1,2}:\d{2})\s*至\s*(?P<end>\d{1,2}:\d{2})',
        text,
    )
    if not match:
        return None
    campus = '创新港' if '创新港' in filename else '兴庆' if '兴庆' in filename else ''
    return {
        'campus': campus,
        'name': match.group('room'),
        'availableTimes': f"{match.group('date')} {match.group('start')}-{match.group('end')}",
    }


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

    from .recurring_time import expand_recurring_entry

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


TIME_FORMAT_HINT = '支持如 2025-05-10 09:00-12:00、周一至周五全天、每周三下午'


def find_unrecognized_time_entries(raw_text):
    """找出既非绝对区间、也非周期性写法的时间条目，供导入时即时提醒。

    判定周期写法时不需要真实排期日期范围，用任意完整一周探测是否可识别。
    """
    from datetime import date as date_cls

    from algorithm import SchedulingError, parse_time_range

    from .recurring_time import expand_recurring_entry

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


class AuthLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')
        key = login_attempt_key(request, username)
        check_login_attempts(key)
        user = authenticate(request, username=username, password=password)
        if not user:
            record_login_failure(key)
            return Response({'error': '账号或密码错误'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(key)
        Token.objects.filter(user=user, created__lte=timezone.now() - timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS)).delete()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'username': user.get_username(),
            'isAdmin': is_admin_user(user),
        })


class AuthLogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({'message': '已退出登录'})


class AuthChangePasswordView(APIView):
    """修改当前登录用户的密码。

    校验原密码与新密码强度；成功后作废旧 Token 并签发新 Token，
    其他已登录端会随旧 Token 一起失效。
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        old_password = str(request.data.get('oldPassword') or '')
        new_password = str(request.data.get('newPassword') or '')
        if not old_password or not new_password:
            return Response({'error': '原密码和新密码不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if not user.check_password(old_password):
            return Response({'error': '原密码不正确'}, status=status.HTTP_400_BAD_REQUEST)
        if new_password == old_password:
            return Response({'error': '新密码不能与原密码相同'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 站点语言是 en-us，这里临时切换到中文让密码强度提示以中文返回
            with translation.override('zh-hans'):
                validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'error': '；'.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({'token': token.key})


class ImportMixin:
    import_header_aliases = {}

    def _get_import_unique_fields(self):
        serializer_class = self.get_serializer_class()
        return getattr(serializer_class, 'import_unique_fields', [])

    def _get_import_header_aliases(self):
        return {**IMPORT_HEADER_ALIASES, **self.import_header_aliases}

    def _normalize_import_unique_value(self, value):
        if isinstance(value, str):
            return value.strip()
        return value

    def prepare_import_row(self, processed_row, filename):
        return processed_row

    def prepare_import_rows(self, prepared_rows, filename):
        return prepared_rows

    def get_import_instance(self, processed_row):
        return None

    def collect_import_warnings(self, processed_row, row_number):
        """行级导入提醒钩子：数据可入库但可能影响排期时返回中文提示列表。"""
        return []

    @action(detail=False, methods=['post'])
    def import_data(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': '未提供文件'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({'error': '文件大小不能超过 5MB'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            filename = file.name.lower()
            header_aliases = self._get_import_header_aliases()
            try:
                df = read_import_dataframe(file, filename, header_aliases)
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            if df.empty:
                return Response({'error': '文件中没有可导入的数据'}, status=status.HTTP_400_BAD_REQUEST)
            if len(df) > MAX_IMPORT_ROWS:
                return Response(
                    {'error': f'单次最多导入 {MAX_IMPORT_ROWS} 行数据'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            df = df.where(df.notnull(), None)
            data_list = df.to_dict(orient='records')
            
            valid_serializers = []
            errors = []
            warnings = []

            batch_unique_values = {}
            prepared_rows = []

            for index, row in enumerate(data_list):
                try:
                    processed_row = {}
                    for k, v in row.items():
                        v = normalize_import_cell(v)
                        if v is None:
                            continue
                        processed_row[k] = v
                        snake_k = ''.join(['_' + i.lower() if i.isupper() else i for i in k]).lstrip('_')
                        if snake_k not in processed_row:
                            processed_row[snake_k] = v

                    processed_row = self.prepare_import_row(processed_row, filename)
                    if not processed_row:
                        continue

                    json_fields = ['roles', 'available_types', 'availableTypes', 'defense_types', 'defenseTypes']
                    for field in json_fields:
                        if field in processed_row and isinstance(processed_row[field], str):
                            val = processed_row[field].strip()
                            if not val:
                                processed_row[field] = []
                            elif (val.startswith('[') and val.endswith(']')) or (val.startswith('{') and val.endswith('}')):
                                try:
                                    processed_row[field] = json.loads(val.replace("'", '"'))
                                except:
                                    processed_row[field] = split_import_list_text(val)
                            else:
                                processed_row[field] = split_import_list_text(val)
                    
                    bool_fields = ['isExternal', 'is_external']
                    for field in bool_fields:
                        if field in processed_row and isinstance(processed_row[field], str):
                            processed_row[field] = processed_row[field].lower() in ['true', '1', '是', 'yes']

                    prepared_rows.append((index + 2, processed_row))
                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'errors': {'non_field_errors': [str(e)]},
                    })

            prepared_rows = self.prepare_import_rows(prepared_rows, filename)

            for row_number, processed_row in prepared_rows:
                try:
                    row_errors = {}
                    for field, message in self._get_import_unique_fields():
                        fields = field if isinstance(field, (tuple, list)) else (field,)
                        values = tuple(
                            self._normalize_import_unique_value(processed_row.get(item))
                            for item in fields
                        )
                        if any(value in (None, '') for value in values):
                            continue
                        key = (tuple(fields), values)
                        if key in batch_unique_values:
                            row_errors[fields[-1]] = [message]
                        else:
                            batch_unique_values[key] = row_number
                    if row_errors:
                        errors.append({
                            'row': row_number,
                            'errors': row_errors,
                        })
                        continue

                    instance = self.get_import_instance(processed_row)
                    serializer = self.get_serializer(
                        instance,
                        data=processed_row,
                        partial=bool(instance),
                    )
                    if serializer.is_valid():
                        valid_serializers.append(serializer)
                        warnings.extend(self.collect_import_warnings(processed_row, row_number))
                    else:
                        errors.append({
                            'row': row_number,
                            'errors': serializer.errors,
                        })
                except Exception as e:
                    errors.append({
                        'row': row_number,
                        'errors': {'non_field_errors': [str(e)]},
                    })

            if errors:
                return Response({
                    'message': '导入失败，请修正错误后重新导入。',
                    'errors': errors[:5],
                    'errorCount': len(errors),
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                for serializer in valid_serializers:
                    serializer.save()

            return Response({
                'message': f'成功导入 {len(valid_serializers)} 条数据',
                'errors': [],
                'warnings': warnings[:5],
                'warningCount': len(warnings),
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': f'解析文件失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': '未提供待删除的 ID 列表'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            queryset = self.get_queryset().filter(id__in=ids)
            count = queryset.count()
            queryset.delete()
            return Response({'message': f'成功删除 {count} 条数据'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'删除失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class TeacherViewSet(AuditedDataMixin, ImportMixin, ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    permission_classes = [IsAdminOrReadOnly]
    import_header_aliases = {
        '可参加答辩类型': 'availableTypes',
        '参加答辩类型': 'availableTypes',
    }

    def collect_import_warnings(self, processed_row, row_number):
        unrecognized = find_unrecognized_time_entries(processed_row.get('unavailableTimes'))
        if not unrecognized:
            return []
        name = processed_row.get('name') or '未知教师'
        return [
            f'第 {row_number} 行 {name}：不可用时间"{"、".join(unrecognized)}"无法识别，'
            f'排期时将被忽略（{TIME_FORMAT_HINT}）'
        ]

    def prepare_import_row(self, processed_row, filename):
        role_value = processed_row.get('roles')
        if not role_value:
            for key, value in processed_row.items():
                if not str(key).startswith('__column_') or not isinstance(value, str):
                    continue
                if any(token in value for token in ['组员', '组长', '主席', '秘书']):
                    role_value = value
                    break

        if isinstance(role_value, str):
            roles = []
            for role in split_import_list_text(role_value):
                if role == '组员':
                    role = '普通专家'
                if role not in roles:
                    roles.append(role)
            processed_row['roles'] = roles

        return processed_row

    @action(detail=False, methods=['post'])
    def import_timetable(self, request):
        """导入课表（矩阵式/行式），把上课时间展开为教师不可用时间条目。

        只更新系统中已有的教师；课表中出现但系统中不存在的姓名会统计返回，
        不会自动创建教师。重复导入按条目字符串去重，幂等。
        """
        file = request.FILES.get('file')
        if not file:
            return Response({'error': '未提供文件'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({'error': '文件大小不能超过 5MB'}, status=status.HTTP_400_BAD_REQUEST)

        first_monday_text = request.data.get('semesterFirstMonday') or request.data.get('semester_first_monday')
        if not first_monday_text:
            return Response(
                {'error': '请提供学期第一周周一的日期（semesterFirstMonday，格式 YYYY-MM-DD）'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            first_monday = datetime.strptime(str(first_monday_text).strip(), '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': '学期起始日期格式必须为 YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
        if first_monday.weekday() != 0:
            return Response(
                {'error': f'{first_monday.isoformat()} 不是周一，请填写学期第一周的周一日期'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = file.name.lower()
        if not filename.endswith(('.xls', '.xlsx', '.csv')):
            return Response({'error': '不支持的文件格式'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            import pandas as pd

            if filename.endswith('.csv'):
                raw = pd.read_csv(file, header=None)
            else:
                raw = pd.read_excel(file, header=None)
        except Exception as exc:
            return Response({'error': f'解析文件失败: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        grid = raw.where(raw.notnull(), None).values.tolist()
        try:
            entries_by_name, warnings = extract_timetable_unavailable_times(
                grid,
                first_monday,
                known_teacher_names=list(Teacher.objects.values_list('name', flat=True)),
            )
        except TimetableParseError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = 0
        matched_names = []
        unknown_names = []
        with transaction.atomic():
            for name in sorted(entries_by_name):
                teacher = Teacher.objects.filter(name=name).first()
                if teacher is None:
                    unknown_names.append(name)
                    continue
                matched_names.append(name)
                existing_entries = split_time_text(teacher.unavailable_times)
                merged_entries = list(existing_entries)
                for entry in entries_by_name[name]:
                    if entry not in merged_entries:
                        merged_entries.append(entry)
                if len(merged_entries) != len(existing_entries):
                    teacher.unavailable_times = '\n'.join(merged_entries)
                    teacher.save(update_fields=['unavailable_times'])
                    updated_count += 1

        return Response({
            'message': f'课表导入完成：更新 {updated_count} 位教师的不可用时间'
                       f'（课表中另有 {len(unknown_names)} 位教师不在系统中，已跳过）',
            'updatedTeachers': updated_count,
            'matchedTeachers': len(matched_names),
            'unknownTeachers': len(unknown_names),
            'unknownTeacherNames': unknown_names[:30],
            'warnings': warnings[:30],
            'entryCount': sum(len(entries) for entries in entries_by_name.values()),
        }, status=status.HTTP_200_OK)


class StudentViewSet(AuditedDataMixin, ImportMixin, ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnly]
    import_header_aliases = {
        '参加答辩类型': 'defenseTypes',
    }

    def _normalize_student_no(self, processed_row):
        """学号统一转为字符串：Excel 数值单元格会被读成 int/float，需去掉小数尾巴"""
        raw = processed_row.get('studentNo')
        if raw is None:
            raw = processed_row.get('student_no')
        if raw is None:
            return None
        text = str(raw).strip()
        if text.endswith('.0'):
            text = text[:-2]
        if not text:
            return None
        processed_row['studentNo'] = text
        processed_row['student_no'] = text
        return text

    def _find_existing_student(self, processed_row):
        """学号优先匹配已有学生；无学号时仅匹配同名且无学号的老记录（避免误并同名不同人）"""
        student_no = processed_row.get('studentNo') or processed_row.get('student_no')
        if student_no:
            existing = Student.objects.filter(student_no=student_no).first()
            if existing:
                return existing
        name = processed_row.get('name')
        if not name:
            return None
        return Student.objects.filter(name=name, student_no__isnull=True).first()

    def prepare_import_row(self, processed_row, filename):
        self._normalize_student_no(processed_row)

        if processed_row.get('campus'):
            processed_row['campus'] = normalize_campus_text(processed_row.get('campus'))

        defense_types = processed_row.get('defenseTypes') or processed_row.get('defense_types')
        if isinstance(defense_types, str):
            defense_types = split_import_list_text(defense_types)
            processed_row['defenseTypes'] = defense_types

        if not defense_types:
            inferred = infer_defense_types_from_filename(filename)
            if inferred:
                defense_types = inferred
                processed_row['defenseTypes'] = defense_types

        existing = self._find_existing_student(processed_row)
        if existing:
            merged_defense_types = list(existing.defense_types or [])
            for defense_type in defense_types or []:
                if defense_type not in merged_defense_types:
                    merged_defense_types.append(defense_type)
            processed_row['defenseTypes'] = merged_defense_types

        return processed_row

    def prepare_import_rows(self, prepared_rows, filename):
        # 初始化批内"无学号姓名"查重状态，由 StudentSerializer.validate 逐行消费，
        # 使同名且无学号的行在对应行号上报 name 字段错误
        self._import_seen_unnumbered_names = set()
        return prepared_rows

    def get_import_instance(self, processed_row):
        return self._find_existing_student(processed_row)


class RoomViewSet(AuditedDataMixin, ImportMixin, ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]

    def collect_import_warnings(self, processed_row, row_number):
        unrecognized = find_unrecognized_time_entries(processed_row.get('availableTimes'))
        if not unrecognized:
            return []
        name = processed_row.get('name') or '未知教室'
        return [
            f'第 {row_number} 行 教室 {name}：可用时间"{"、".join(unrecognized)}"无法识别，'
            f'排期时将按全时段可用处理（{TIME_FORMAT_HINT}）'
        ]

    def prepare_import_row(self, processed_row, filename):
        if not processed_row.get('name'):
            combined_text = ' '.join(str(value) for value in processed_row.values() if value is not None)
            card_row = parse_card_style_room_text(combined_text, filename)
            if card_row:
                processed_row.update(card_row)
            if not processed_row.get('name') and any(str(key).startswith('__column_') for key in processed_row):
                return None
            if not processed_row.get('name') and '教室借用申请' in filename:
                return None

        if processed_row.get('campus'):
            processed_row['campus'] = normalize_campus_text(processed_row.get('campus'))

        if not processed_row.get('availableTimes') and processed_row.get('useDate') and processed_row.get('useTime'):
            processed_row['availableTimes'] = (
                f"{processed_row.get('useDate')} {normalize_class_period_time(processed_row.get('useTime'))}"
            ).strip()

        return processed_row

    def prepare_import_rows(self, prepared_rows, filename):
        merged = {}
        ordered = []
        for row_number, row in prepared_rows:
            key = (
                self._normalize_import_unique_value(row.get('campus') or ''),
                self._normalize_import_unique_value(row.get('name') or ''),
            )
            if not all(key):
                ordered.append((row_number, row))
                continue
            if key not in merged:
                merged[key] = (row_number, row)
                ordered.append((row_number, row))
                continue

            existing_row = merged[key][1]
            if not existing_row.get('availableTimes') and not row.get('availableTimes'):
                ordered.append((row_number, row))
                continue

            current_times = split_time_text(existing_row.get('availableTimes', ''))
            next_times = split_time_text(row.get('availableTimes', ''))
            for time_text in next_times:
                if time_text not in current_times:
                    current_times.append(time_text)
            existing_row['availableTimes'] = ','.join(current_times)

        return ordered


class RuleConfigViewSet(AuditedDataMixin, ModelViewSet):
    queryset = RuleConfig.objects.all()
    serializer_class = RuleConfigSerializer
    permission_classes = [IsAdminOrReadOnly]

    def list(self, request, *args, **kwargs):
        defense_type = request.query_params.get('defense_type', 'pre')
        rule_config = RuleConfig.objects.filter(defense_type=defense_type).first()
        if not rule_config:
            return Response(default_rule_config(defense_type))
        return Response(self.get_serializer(rule_config).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class OperationLogViewSet(ModelViewSet):
    queryset = OperationLog.objects.all()
    serializer_class = OperationLogSerializer
    permission_classes = [IsAdminOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(operator=self.request.user.get_username(), authoritative=False)

    def update(self, request, *args, **kwargs):
        return Response({'error': '操作日志不允许修改'}, status=405)

    def destroy(self, request, *args, **kwargs):
        return Response({'error': '操作日志不允许删除，请使用归档备份'}, status=405)

    def clear(self, request):
        OperationLog.objects.filter(authoritative=False).delete()
        return Response({'message': '客户端记录已清空，服务端审计记录已保留'}, status=status.HTTP_200_OK)


class ScheduleViewSet(GenericViewSet):
    queryset = ScheduleVersion.objects.all()
    serializer_class = ScheduleVersionSerializer
    read_actions = {'current', 'export', 'export_excel', 'export_word', 'check_conflicts', 'versions'}

    def get_permissions(self):
        if self.action in self.read_actions:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    # 算法/检测产生的英文冲突类型 → 前端 ScheduleConflict 的中文类型与级别
    CONFLICT_TYPE_LABELS = {
        **{key: (label, 'error') for key, label in {
            'duplicate_student': '学生重复分组', 'missing_student': '学生未分组',
            'teacher_unavailable': '人员不可用', 'role_conflict': '人员角色冲突',
            'room_capacity': '教室容量不足',
        }.items()},
        'time_conflict': ('时间冲突', 'error'),
        'teacher_time_conflict': ('时间冲突', 'error'),
        'room_conflict': ('教室冲突', 'error'),
        'room_or_time_unavailable': ('教室冲突', 'error'),
        'insufficient_experts': ('人员冲突', 'error'),
        'chair_unavailable': ('人员冲突', 'error'),
        'secretary_unavailable': ('人员冲突', 'error'),
        'supervisor_avoidance': ('导师回避冲突', 'error'),
        'supervisor_missing': ('导师未与学生同组', 'error'),
        'secretary_student_conflict': ('秘书学生冲突', 'error'),
        'secretary_is_supervisor': ('秘书学生冲突', 'error'),
        'secretary_continuity_broken': ('秘书连续性提示', 'warning'),
        'campus_mismatch': ('校区切换提示', 'warning'),
        'student_defense_type_missing': ('数据完整性提示', 'warning'),
        'group_size_out_of_range': ('人数规则冲突', 'error'),
        'invalid_time_format': ('数据完整性提示', 'error'),
        'mentor_not_found': ('数据完整性提示', 'warning'),
        'mentor_unavailable_for_defense': ('数据完整性提示', 'warning'),
        'secretary_not_found': ('数据完整性提示', 'warning'),
        'secretary_unavailable_for_defense': ('数据完整性提示', 'warning'),
    }

    # 历史/前端旧版规则键 → 算法使用的规则键
    RULE_KEY_ALIASES = {
        'mentor_avoidance': 'avoid_supervisor',
    }

    def _normalize_rules(self, rules):
        """统一规则键：兼容旧键名别名，并补齐 defense_type 缺省值"""
        normalized = dict(rules or {})
        for alias, canonical in self.RULE_KEY_ALIASES.items():
            if alias in normalized and canonical not in normalized:
                normalized[canonical] = normalized[alias]
        normalized.setdefault('defense_type', 'pre')
        return normalized

    def _format_conflicts(self, schedule_version, raw_conflicts):
        """把英文冲突结构转换为前端 ScheduleConflict 形状（中文类型 + level/target/reason）"""
        group_name_map = {g.id: g.group_id for g in schedule_version.groups.all()}
        defense_label = schedule_version.get_defense_type_display()
        created_at = timezone.localtime(schedule_version.created_at).isoformat()

        formatted = []
        for index, item in enumerate(raw_conflicts or [], start=1):
            raw_type = item.get('type', '')
            label, level = self.CONFLICT_TYPE_LABELS.get(raw_type, (raw_type or '未知冲突', 'warning'))
            if raw_type == 'insufficient_experts':
                # 专家数达到配置下限时降级为警告，未达下限保持错误
                min_required = item.get('min_required') or 0
                if min_required and (item.get('assigned') or 0) >= min_required:
                    level = 'warning'

            group_ids = [
                gid for gid in (item.get('group_db_ids') or item.get('group_ids') or [])
                if gid in group_name_map
            ]
            if not group_ids and item.get('group_id') in group_name_map:
                group_ids = [item['group_id']]

            target = item.get('teacher_name') or item.get('room_name') or ''
            if not target and group_ids:
                target = group_name_map.get(group_ids[0], '')

            formatted.append({
                'id': index,
                'defenseType': defense_label,
                'groupId': group_ids[0] if group_ids else None,
                'groupName': group_name_map.get(group_ids[0], '') if group_ids else '',
                'type': label,
                'level': level,
                'target': target,
                'reason': item.get('description', ''),
                'relatedGroupIds': group_ids,
                'createdAt': created_at,
            })
        return formatted

    def _build_algorithm_input(self, defense_type, date_range=None):
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
        students = list(Student.objects.all())
        rooms = list(Room.objects.all())

        all_teachers = list(Teacher.objects.all())
        teachers = [
            teacher for teacher in all_teachers
            if not (teacher.available_types or []) or defense_label in teacher.available_types
        ]
        teacher_name_counts = {}
        for teacher in teachers:
            teacher_name_counts[teacher.name] = teacher_name_counts.get(teacher.name, 0) + 1
        duplicate_teacher_names = sorted(name for name, count in teacher_name_counts.items() if count > 1)
        if duplicate_teacher_names:
            raise ValueError(f'教师姓名重复，无法可靠匹配导师/秘书：{"、".join(duplicate_teacher_names)}')
        teacher_by_name = {teacher.name: teacher for teacher in teachers}
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
                'available_time': unavailable_times,
                'availability_invalid': bool(invalid_times),
                'campus_preference': teacher.campus_preference,
                'forbidden_with': forbidden_with,
            })

        # 正式答辩沿用预答辩分组：把预答辩当前版本的组号随学生传给算法
        previous_group_map = {}
        if defense_type == 'formal':
            previous_version = ScheduleVersion.objects.filter(
                defense_type='pre', is_current=True
            ).first()
            if previous_version:
                for previous_group in previous_version.groups.prefetch_related('students'):
                    for member in previous_group.students.all():
                        previous_group_map[member.id] = previous_group.id

        student_payload = []
        missing_type_students = []
        for student in students:
            defense_types = student.defense_types or []
            if not defense_types:
                missing_type_students.append(student)
                continue
            if defense_label not in defense_types:
                continue

            mentor_name = (student.mentor_name or '').strip()
            secretary_name = (student.secretary_name or '').strip()
            mentor = teacher_by_name.get(mentor_name) if mentor_name else None
            secretary = teacher_by_name.get(secretary_name) if secretary_name else None

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
                from .recurring_time import is_no_limit_entry

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
            from .recurring_time import is_no_limit_entry
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

    @staticmethod
    def _extract_rule_date_range(rules):
        """从规则中提取排期日期范围（date 元组），供周期性时间描述展开；无效时返回 None"""
        try:
            start = datetime.strptime(str(rules.get('start_date') or ''), '%Y-%m-%d').date()
            end = datetime.strptime(str(rules.get('end_date') or ''), '%Y-%m-%d').date()
        except ValueError:
            return None
        if end < start:
            return None
        return (start, end)

    @action(detail=False, methods=['post'])
    @schedule_write
    def generate(self, request):
        """一键生成排期"""
        if not isinstance(request.data.get('rules', {}), dict):
            return Response({'error': '排期规则必须是对象'}, status=400)
        rules = self._normalize_rules(request.data.get('rules', {
            'defense_type': 'pre',
            'start_date': '2025-05-10',
            'avoid_weekend': True,
            'avoid_holiday': True,
        }))

        if rules['defense_type'] not in DEFENSE_TYPE_LABELS:
            return Response({'error': '未知答辩类型'}, status=400)
        request_key = request.data.get('request_key')
        if request_key and (not isinstance(request_key, str) or len(request_key) > 64):
            return Response({'error': '请求标识格式不正确'}, status=400)
        if request_key:
            previous = ScheduleVersion.objects.filter(request_key=request_key).first()
            if previous:
                if previous.rules_snapshot != rules:
                    return Response({'error': '该请求标识已用于其他规则，请重新生成'}, status=409)
                return Response(self._version_result(previous))
        defense_label = DEFENSE_TYPE_LABELS.get(rules['defense_type'], rules['defense_type'])

        try:
            input_payload, data_notices = self._build_algorithm_input(
                rules['defense_type'],
                date_range=self._extract_rule_date_range(rules),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not input_payload['students']:
            return Response(
                {'error': f'没有学生参加【{defense_label}】，请检查学生数据中的"参加答辩类型"设置'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not input_payload['teachers']:
            return Response(
                {'error': f'没有可参加【{defense_label}】的教师，请检查教师数据中的"可参加答辩类型"设置'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        input_data = {**input_payload, 'rules': rules}

        try:
            from algorithm import SchedulingError, generate_schedule
            result = generate_schedule(**input_data)
        except ImportError as exc:
            return Response({'error': f'排期算法加载失败: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except SchedulingError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError) as exc:
            return Response({'error': f'排期参数错误: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for previous in ScheduleVersion.objects.filter(defense_type=rules['defense_type'], is_current=True):
                self._freeze_version(previous)
            ScheduleVersion.objects.filter(defense_type=rules['defense_type']).update(is_current=False)

            version_num = (ScheduleVersion.objects.filter(defense_type=rules['defense_type']).aggregate(n=Max('version'))['n'] or 0) + 1
            schedule_version = ScheduleVersion.objects.create(
                version=version_num,
                defense_type=rules['defense_type'],
                rules_snapshot=rules,
                input_snapshot=input_payload,
                request_key=request_key or None,
                is_current=True
            )

            # 算法冲突里的组编号是 "G1" 这类字符串，入库后补上数据库组 ID 便于前端定位
            group_db_map = {}
            for group_data in result.get('groups', []):
                group = Group.objects.create(
                    schedule_version=schedule_version,
                    group_id=group_data['group_id'],
                    time=group_data.get('time') or '',
                    room_id=group_data.get('room_id'),
                    campus=group_data.get('campus') or '',
                    chair_id=group_data.get('chair_id'),
                    secretary_id=group_data.get('secretary_id')
                )
                group_db_map[group_data['group_id']] = group.id
                group.experts.add(*group_data.get('expert_ids', []))
                group.students.add(*group_data.get('student_ids', []))

            conflicts_snapshot = list(data_notices)
            for item in result.get('conflicts', []):
                enriched = dict(item)
                enriched['group_db_ids'] = [
                    group_db_map[related]
                    for related in item.get('related_ids', [])
                    if isinstance(related, str) and related in group_db_map
                ]
                conflicts_snapshot.append(enriched)

            schedule_version.conflicts_snapshot = conflicts_snapshot
            schedule_version.save(update_fields=['conflicts_snapshot'])

            # 预答辩确定的秘书回写学生档案："学生从预答辩开始全程跟着同一个秘书"，
            # 正式答辩生成时依据该绑定沿用秘书并保持组不变
            if rules['defense_type'] == 'pre':
                self._sync_student_secretaries(schedule_version)

        return Response(self._version_result(schedule_version))

    def _sync_student_secretaries(self, schedule_version):
        """把预答辩各组的秘书写回组内学生的"对应秘书姓名"字段"""
        for group in schedule_version.groups.select_related('secretary').prefetch_related('students'):
            if not group.secretary:
                continue
            secretary_name = group.secretary.name
            for student in group.students.all():
                if student.secretary_name != secretary_name:
                    student.secretary_name = secretary_name
                    student.save(update_fields=['secretary_name'])

    def _mock_schedule_result(self, input_data):
        return {
            'groups': [
                {
                    'group_id': 'G1',
                    'time': '2025-05-10 09:00-12:00',
                    'room_id': 1,
                    'campus': '创新港',
                    'chair_id': 1,
                    'expert_ids': [2, 3],
                    'secretary_id': 4,
                    'student_ids': [101, 102, 103]
                }
            ],
            'conflicts': []
        }

    @action(detail=False, methods=['get'])
    def current(self, request):
        """获取当前生效的排期"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response({
                'defenseType': defense_type,
                'generatedAt': '',
                'groups': [],
                'conflicts': [],
                'message': '暂无排期结果'
            })

        return Response(self._version_result(schedule_version))

    def _selected_version(self, request, defense_type):
        from rest_framework.exceptions import ValidationError
        queryset = ScheduleVersion.objects.filter(defense_type=defense_type)
        if not is_admin_user(request.user):
            queryset = queryset.filter(status='published')
        version_id = request.query_params.get('version_id') or request.data.get('version_id')
        if version_id:
            try:
                return queryset.filter(pk=int(version_id)).first()
            except (ValueError, TypeError):
                raise ValidationError('版本 ID 格式不正确')
        return queryset.filter(is_current=True).first() if is_admin_user(request.user) else queryset.first()

    def _version_result(self, schedule_version):
        if schedule_version.result_snapshot:
            return {**schedule_version.result_snapshot, 'status': schedule_version.status, 'revision': schedule_version.revision, 'isCurrent': schedule_version.is_current}
        groups = export_groups(schedule_version)
        formatted_groups = []
        for group in groups:
            time_parts = group.time.split(' ')
            date = time_parts[0] if len(time_parts) > 0 else ''
            time_range = time_parts[1] if len(time_parts) > 1 else ''

            formatted_groups.append({
                'id': group.id,
                'defenseType': schedule_version.get_defense_type_display(),
                'groupName': group.group_id,
                'campus': group.campus,
                'classroom': group.room.name if group.room else '未分配',
                'date': date,
                'timeRange': time_range,
                'chairman': group.chair.name if group.chair else None,
                'secretary': group.secretary.name if group.secretary else '未分配',
                'chairTitle': group.chair.title if group.chair else '',
                'chairId': group.chair_id,
                'secretaryId': group.secretary_id,
                'teachers': [
                    {'id': t.id, 'name': t.name, 'title': t.title, 'roles': getattr(t, 'roles', []), 'isExternal': t.is_external}
                    for t in group.experts.all()
                ],
                'students': [
                    {
                        'id': s.id, 
                        'name': s.name, 
                        'studentType': s.student_type,
                        'mentorName': s.mentor_name
                    }
                    for s in group.students.all()
                ]
            })

        return {
            'isCurrent': schedule_version.is_current,
            'versionId': schedule_version.id,
            'version': schedule_version.version,
            'revision': schedule_version.revision,
            'status': schedule_version.status,
            'rules': schedule_version.rules_snapshot,
            'defenseType': schedule_version.get_defense_type_display(),
            'generatedAt': timezone.localtime(schedule_version.created_at).strftime('%Y-%m-%d %H:%M'),
            'groups': formatted_groups,
            'conflicts': self._format_conflicts(schedule_version, self._check_conflicts(schedule_version))
        }

    @action(detail=False, methods=['post'], url_path='adjust-group')
    @schedule_write
    def adjust_group(self, request):
        """保存前端完整分组编辑表单。"""
        group_id = request.data.get('group_id')
        group_data = request.data.get('group_data') or {}
        if not isinstance(group_data, dict):
            return Response({'error': '分组数据格式不正确'}, status=400)
        for key in ('teachers', 'students'):
            if key in group_data and (not isinstance(group_data[key], list) or any(
                    not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] <= 0
                    for item in group_data[key])):
                return Response({'error': f'{key} 必须提供有效的人员 ID 列表'}, status=400)
        if not group_id or not group_data:
            return Response({'error': '缺少必要参数'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=status.HTTP_404_NOT_FOUND)

        next_group_id = group_data.get('groupName') or group.group_id
        if not isinstance(next_group_id, str) or len(next_group_id) > 20:
            return Response({'error': '组名必须为不超过 20 个字符的文本'}, status=400)
        date = group_data.get('date')
        time_range = group_data.get('timeRange')
        next_time = group.time
        if date and time_range:
            try:
                next_time = validate_schedule_time_text(f'{date} {time_range}')
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        next_campus = group_data.get('campus') or group.campus

        room = None
        room_name = group_data.get('classroom')
        if room_name:
            room = Room.objects.filter(name=room_name, campus=next_campus).first()
            if not room:
                return Response({'error': f'教室不存在: {room_name}'}, status=status.HTTP_400_BAD_REQUEST)

        chair = None
        chair_name = group_data.get('chairman') or group_data.get('leader')
        if chair_name:
            chair = Teacher.objects.filter(name=chair_name).first()
            if not chair:
                return Response({'error': f'主席/组长不存在: {chair_name}'}, status=status.HTTP_400_BAD_REQUEST)

        secretary = None
        secretary_name = group_data.get('secretary')
        if secretary_name:
            secretary = Teacher.objects.filter(name=secretary_name).first()
            if not secretary:
                return Response({'error': f'秘书不存在: {secretary_name}'}, status=status.HTTP_400_BAD_REQUEST)

        teacher_ids = [item.get('id') for item in group_data.get('teachers', []) if item.get('id')]
        student_ids = [item.get('id') for item in group_data.get('students', []) if item.get('id')]
        if teacher_ids:
            existing_teacher_ids = set(Teacher.objects.filter(id__in=teacher_ids).values_list('id', flat=True))
            missing_teacher_ids = sorted(set(teacher_ids) - existing_teacher_ids)
            if missing_teacher_ids:
                return Response({'error': f'教师不存在: {missing_teacher_ids}'}, status=status.HTTP_400_BAD_REQUEST)
        if student_ids:
            existing_student_ids = set(Student.objects.filter(id__in=student_ids).values_list('id', flat=True))
            missing_student_ids = sorted(set(student_ids) - existing_student_ids)
            if missing_student_ids:
                return Response({'error': f'学生不存在: {missing_student_ids}'}, status=status.HTTP_400_BAD_REQUEST)

        if len(student_ids) != len(set(student_ids)):
            return Response({'error': '学生列表包含重复人员'}, status=400)
        if Group.objects.filter(schedule_version=group.schedule_version, students__id__in=student_ids).exclude(pk=group.pk).exists():
            return Response({'error': '学生已在其他组，请使用移动学生操作'}, status=400)
        if Group.objects.filter(schedule_version=group.schedule_version, group_id=next_group_id).exclude(pk=group.pk).exists():
            return Response({'error': '同一版本内组名不能重复'}, status=400)
        if 'students' in group_data and group.students.exclude(pk__in=student_ids).exists():
            return Response({'error': '请使用移动学生操作将学生调到目标组，不能直接移除已分组学生'}, status=400)
        with transaction.atomic():
            group.group_id = next_group_id
            group.time = next_time
            group.campus = next_campus
            if room:
                group.room = room
            if chair:
                group.chair = chair
            if secretary:
                group.secretary = secretary
            group.save()
            if 'teachers' in group_data:
                group.experts.set(teacher_ids)
            if 'students' in group_data:
                group.students.set(student_ids)

        return Response({
            'success': True,
            'message': '调整保存成功',
            'updatedGroup': group_data,
            'conflicts': self._check_conflicts(group.schedule_version),
        })

    @action(detail=False, methods=['post'])
    @schedule_write
    def adjust(self, request):
        """人工调整：移动学生、更换专家、修改时间/教室"""
        action_type = request.data.get('action')

        if action_type == 'move_student':
            return self._move_student(request)
        elif action_type == 'change_expert':
            return self._change_expert(request)
        elif action_type == 'change_time':
            return self._change_time(request)
        elif action_type == 'change_room':
            return self._change_room(request)
        elif action_type == 'change_chair':
            return self._change_chair(request)
        elif action_type == 'change_secretary':
            return self._change_secretary(request)
        else:
            return Response(
                {'error': f'未知的 action: {action_type}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], url_path='export_word')
    def export_word(self, request):
        """导出当前排期为 Word 时间安排表（版式对齐学院归档样例，导师与学生同色）"""
        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response({'error': '暂无排期结果可导出'}, status=404)

        from urllib.parse import quote

        from .export_word import export_schedule_word

        defense_label = DEFENSE_TYPE_LABELS.get(defense_type, defense_type)
        doc = export_schedule_word(schedule_version, defense_label)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        ascii_name = f'defense_schedule_{defense_type}.docx'
        utf8_name = quote(f'{defense_label}时间安排.docx')
        response['Content-Disposition'] = (
            f"attachment; filename={ascii_name}; filename*=UTF-8''{utf8_name}"
        )
        doc.save(response)
        return response

    @action(detail=False, methods=['get'])
    def export(self, request):
        """导出当前排期为 Excel 文件"""
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        from .export_colors import build_mentor_color_map

        defense_type = request.query_params.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response({'error': '暂无排期结果可导出'}, status=404)

        wb = Workbook()
        default_sheet = wb.active
        wb.remove(default_sheet)

        groups = list(export_groups(schedule_version))

        # 导师与其学生同色（与 Word 导出同一套配色语义）
        mentor_color_map = build_mentor_color_map(groups)
        mentor_titles = dict(Teacher.objects.values_list('name', 'title'))

        for group in groups:
            sheet = wb.create_sheet(title=f"组{group.group_id}")

            sheet.column_dimensions['A'].width = 15
            sheet.column_dimensions['B'].width = 20
            sheet.column_dimensions['C'].width = 15
            sheet.column_dimensions['D'].width = 25

            title_font = Font(bold=True, size=14)
            title_cell = sheet['A1']
            title_cell.value = f"答辩排期表 - {group.group_id}"
            title_cell.font = title_font
            sheet.merge_cells('A1:D1')

            row = 3
            chair_name = group.chair.name if group.chair else '未分配'
            info_data = [
                ('时间', group.time, None),
                ('教室', group.room.name if group.room else '未分配', None),
                ('校区', group.campus, None),
                ('主席/组长', chair_name, mentor_color_map.get(chair_name)),
                ('秘书', group.secretary.name if group.secretary else '未分配', None),
            ]

            for label, value, value_color in info_data:
                sheet[f'A{row}'] = label
                sheet[f'B{row}'] = value
                sheet[f'A{row}'].font = Font(bold=True)
                if value_color:
                    sheet[f'B{row}'].font = Font(color=value_color, bold=True)
                row += 1

            sheet[f'A{row}'] = '专家'
            sheet[f'A{row}'].font = Font(bold=True)
            expert_names = [e.name for e in group.experts.all()]
            # 专家逐名着色（富文本）：专家若是某学生导师则与其学生同色
            if expert_names:
                from openpyxl.cell.rich_text import CellRichText, TextBlock
                from openpyxl.cell.text import InlineFont

                rich_parts = []
                for expert_index, expert_name in enumerate(expert_names):
                    if expert_index:
                        rich_parts.append('、')
                    expert_color = mentor_color_map.get(expert_name)
                    if expert_color:
                        rich_parts.append(TextBlock(InlineFont(color=expert_color, b=True), expert_name))
                    else:
                        rich_parts.append(expert_name)
                sheet[f'B{row}'] = CellRichText(*rich_parts)
            else:
                sheet[f'B{row}'] = '未分配'
            row += 2

            headers = ['学生姓名', '学生类型', '导师姓名', '导师职称']
            for col, header in enumerate(headers, 1):
                cell = sheet.cell(row=row, column=col, value=header)
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')

            row += 1

            for student in group.students.all():
                mentor_name = (student.mentor_name or '').strip()
                mentor_color = mentor_color_map.get(mentor_name)
                # 学生与其导师同色（字体着色），未匹配到导师时保持默认黑色
                row_font = Font(color=mentor_color, bold=True) if mentor_color else Font()

                cell = sheet.cell(row=row, column=1, value=student.name)
                cell.font = row_font

                cell = sheet.cell(row=row, column=2, value=student.student_type)
                cell.font = row_font

                cell = sheet.cell(row=row, column=3, value=mentor_name or '未分配')
                cell.font = row_font

                supervisor_title = getattr(student, 'mentor_title', mentor_titles.get(student.mentor_name, ''))
                cell = sheet.cell(row=row, column=4, value=supervisor_title)
                cell.font = row_font

                row += 1

            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

            for r in range(3, row):
                for c in range(1, 5):
                    cell = sheet.cell(row=r, column=c)
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center', vertical='center')

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=defense_schedule_{defense_type}.xlsx'

        wb.save(response)
        return response

    @action(detail=False, methods=['get'], url_path='export-excel')
    def export_excel(self, request):
        defense_type = request.query_params.get('defense_type')
        defense_label = request.query_params.get('defenseType')
        if not defense_type and defense_label:
            defense_type = {'预答辩': 'pre', '正式答辩': 'formal', '中期答辩': 'mid'}.get(defense_label, defense_label)

        request.GET._mutable = True
        request.GET['defense_type'] = defense_type or 'pre'
        return self.export(request)

    @action(detail=False, methods=['post'], url_path='check-conflicts')
    def check_conflicts(self, request):
        """检测当前排期冲突"""
        defense_type = request.data.get('defense_type', 'pre')
        schedule_version = self._selected_version(request, defense_type)

        if not schedule_version:
            return Response([], status=status.HTTP_200_OK)

        return Response(
            self._format_conflicts(schedule_version, self._check_conflicts(schedule_version)),
            status=status.HTTP_200_OK,
        )

    def _move_student(self, request):
        student_id = request.data.get('student_id')
        from_group_id = request.data.get('from_group_id')
        to_group_id = request.data.get('to_group_id')

        if not all([student_id, from_group_id, to_group_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            from_group = Group.objects.select_related('schedule_version').get(id=from_group_id)
            to_group = Group.objects.get(id=to_group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        student = Student.objects.filter(id=student_id).first()
        if not student:
            return Response({'error': f'学生不存在: {student_id}'}, status=400)
        if not from_group.students.filter(id=student.id).exists():
            return Response({'error': f'学生不在原组: {student_id}'}, status=400)

        with transaction.atomic():
            from_group.students.remove(student)
            to_group.students.add(student)
            # 预答辩阶段移动学生后，学生跟随目标组的秘书（保持跨场次绑定一致）
            if from_group.schedule_version.defense_type == 'pre':
                new_secretary_name = to_group.secretary.name if to_group.secretary else ''
                if student.secretary_name != new_secretary_name:
                    student.secretary_name = new_secretary_name
                    student.save(update_fields=['secretary_name'])

        conflicts = self._check_conflicts(from_group.schedule_version)

        return Response({
            'status': 'ok',
            'message': f'学生 {student_id} 已从组 {from_group_id} 移动到组 {to_group_id}',
            'conflicts': conflicts
        })

    def _change_expert(self, request):
        group_id = request.data.get('group_id')
        old_expert_id = request.data.get('old_expert_id')
        new_expert_id = request.data.get('new_expert_id')

        if not all([group_id, old_expert_id, new_expert_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        old_expert = Teacher.objects.filter(id=old_expert_id).first()
        new_expert = Teacher.objects.filter(id=new_expert_id).first()
        missing_ids = [
            teacher_id
            for teacher_id, teacher in ((old_expert_id, old_expert), (new_expert_id, new_expert))
            if teacher is None
        ]
        if missing_ids:
            return Response({'error': f'教师不存在: {missing_ids}'}, status=400)
        if not group.experts.filter(id=old_expert.id).exists():
            return Response({'error': f'原专家不在当前组: {old_expert_id}'}, status=400)

        with transaction.atomic():
            group.experts.remove(old_expert)
            group.experts.add(new_expert)

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '专家已更换',
            'conflicts': conflicts
        })

    def _change_chair(self, request):
        group_id = request.data.get('group_id')
        new_chair_id = request.data.get('new_chair_id')

        if not all([group_id, new_chair_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        chair = Teacher.objects.filter(id=new_chair_id).first()
        if not chair:
            return Response({'error': f'主席不存在: {new_chair_id}'}, status=400)

        group.chair = chair
        group.save()

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '主席已更换',
            'conflicts': conflicts
        })

    def _change_secretary(self, request):
        group_id = request.data.get('group_id')
        new_secretary_id = request.data.get('new_secretary_id')

        if not all([group_id, new_secretary_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        secretary = Teacher.objects.filter(id=new_secretary_id).first()
        if not secretary:
            return Response({'error': f'秘书不存在: {new_secretary_id}'}, status=400)

        group.secretary = secretary
        group.save()

        # 预答辩阶段手动更换秘书时同步学生绑定，保持"学生跟随同一秘书"
        if group.schedule_version.defense_type == 'pre':
            for student in group.students.all():
                if student.secretary_name != secretary.name:
                    student.secretary_name = secretary.name
                    student.save(update_fields=['secretary_name'])

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '秘书已更换',
            'conflicts': conflicts
        })

    def _change_time(self, request):
        group_id = request.data.get('group_id')
        new_time = request.data.get('new_time')

        if not all([group_id, new_time]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            normalized_time = validate_schedule_time_text(new_time)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
            group.time = normalized_time
            group.save()

            conflicts = self._check_conflicts(group.schedule_version)

            return Response({
                'status': 'ok',
                'message': f'时间已修改为 {normalized_time}',
                'conflicts': conflicts
            })
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

    def _change_room(self, request):
        group_id = request.data.get('group_id')
        new_room_id = request.data.get('new_room_id')

        if not all([group_id, new_room_id]):
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            group = Group.objects.select_related('schedule_version').get(id=group_id)
        except Group.DoesNotExist:
            return Response({'error': '组不存在'}, status=404)

        room = Room.objects.filter(id=new_room_id).first()
        if not room:
            return Response({'error': f'教室不存在: {new_room_id}'}, status=400)

        group.room = room
        group.save()

        conflicts = self._check_conflicts(group.schedule_version)

        return Response({
            'status': 'ok',
            'message': '教室已更换',
            'conflicts': conflicts
        })

    def _check_conflicts(self, schedule_version):
        from algorithm import (GroupDraft, SchedulingError, detect_global_conflicts,
                               parse_teacher, parse_student, parse_room, parse_time_range, deduplicate_conflicts)
        if schedule_version.result_snapshot or schedule_version.export_snapshot:
            return schedule_version.conflicts_snapshot
        rules = schedule_version.rules_snapshot or {}
        payload, notices = self._build_algorithm_input(schedule_version.defense_type, self._extract_rule_date_range(rules))
        drafts, group_map = [], {}
        for group in schedule_version.groups.select_related('room', 'chair', 'secretary').prefetch_related('experts', 'students'):
            group_map[group.group_id] = group.id
            try:
                slot = parse_time_range(group.time) if group.time else None
            except SchedulingError:
                slot = None
            drafts.append(GroupDraft(group.group_id, group.campus, [s.id for s in group.students.all()],
                slot, group.room_id, group.chair_id, [t.id for t in group.experts.all()], group.secretary_id))
        conflicts = detect_global_conflicts(drafts, [parse_student(s) for s in payload['students']],
            [parse_teacher(t) for t in payload['teachers']], [parse_room(r) for r in payload['rooms']], rules)
        for conflict in conflicts:
            conflict['group_db_ids'] = [group_map[g] for g in conflict.get('related_ids', []) if isinstance(g, str) and g in group_map]
        return deduplicate_conflicts(notices + conflicts)

    def _freeze_version(self, version):
        if version.result_snapshot:
            return
        version.conflicts_snapshot = self._check_conflicts(version)
        version.result_snapshot = self._version_result(version)
        version.export_snapshot = capture_export_groups(version)
        version.save(update_fields=['conflicts_snapshot', 'result_snapshot', 'export_snapshot'])

    @action(detail=False, methods=['get'])
    def versions(self, request):
        queryset = ScheduleVersion.objects.filter(defense_type=request.query_params.get('defense_type', 'pre'))
        if not is_admin_user(request.user):
            queryset = queryset.filter(status='published')
        return Response(list(queryset.values('id', 'version', 'status', 'is_current', 'created_at', 'published_at', 'revision')[:100]))

    @action(detail=False, methods=['post'])
    @schedule_write
    def publish(self, request):
        try:
            version = ScheduleVersion.objects.get(pk=request.data.get('version_id'), is_current=True)
        except (ScheduleVersion.DoesNotExist, ValueError, TypeError):
            return Response({'error': '当前草稿不存在，请刷新'}, status=404)
        if str(request.data.get('expected_revision')) != str(version.revision):
            return Response({'error': '排期已发生变化，请刷新后重新发布'}, status=409)
        if version.status == 'published':
            return Response(self._version_result(version))
        conflicts = self._format_conflicts(version, self._check_conflicts(version))
        if any(c['level'] == 'error' for c in conflicts):
            return Response({'error': '仍存在必须处理的冲突，不能发布', 'conflicts': conflicts}, status=400)
        if not version.groups.exists():
            return Response({'error': '空排期不能发布'}, status=400)
        version.status = 'published'
        version.published_at = timezone.now()
        version.revision += 1
        version.save(update_fields=['status', 'published_at', 'revision'])
        self._freeze_version(version)
        audit(request, '发布', f'发布 {version.defense_type} v{version.version}', version_id=version.id)
        return Response(self._version_result(version))

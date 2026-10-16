from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
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
    '是否启用': 'isActive',
    '是否适合当组员': 'memberEligible',
    '是否可担任普通专家': 'memberEligible',
    '软件学院导师': 'isSoftwareTeacher',
    '是否软件学院导师': 'isSoftwareTeacher',
    '导师编号': 'mentorId',
    '秘书编号': 'secretaryId',
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
    'isActive', 'is_active', 'memberEligible', 'member_eligible', 'isSoftwareTeacher', 'is_software_teacher',
    'mentorId', 'secretaryId',
    'availableTypes', 'available_types', 'campusPreference', 'campus_preference',
    'unavailableTimes', 'unavailable_times', 'avoidTeacherNames', 'avoid_teacher_names',
    'remark', 'studentType', 'student_type', 'mentorName', 'mentor_name', 'campus',
    'studentNo', 'student_no', 'gender',
    'defenseTypes', 'defense_types', 'secretaryName', 'secretary_name', 'capacity',
    'availableTimes', 'available_times', 'useDate', 'use_date', 'useTime', 'use_time',
}




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








TIME_FORMAT_HINT = '支持如 2025-05-10 09:00-12:00、周一至周五全天、每周三下午'




class AuthLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        # 账号与密码两端空白一律忽略：从记事本复制 24 位初始随机密码时常带入空格，
        # 会造成认证失败，而界面只提示"账号或密码错误"，极易误判为服务异常。
        username = str(request.data.get('username') or '').strip()
        password = str(request.data.get('password') or '').strip()
        key = login_attempt_key(request, username)
        check_login_attempts(key)
        user = authenticate(request, username=username, password=password)
        if not user:
            record_login_failure(key)
            return Response({'error': '账号或密码错误'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(key)
        # 本视图只调用 authenticate()，不经过 auth.login()，需手动记录登录时间
        update_last_login(None, user)
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
        # 与登录口径保持一致：密码两端空白一律忽略，
        # 否则可能设置出带尾空格的密码，之后登录时又被忽略掉而无法通过。
        old_password = str(request.data.get('oldPassword') or '').strip()
        new_password = str(request.data.get('newPassword') or '').strip()
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
                    
                    bool_fields = ['isExternal', 'is_external', 'isActive', 'is_active',
                        'memberEligible', 'member_eligible', 'isSoftwareTeacher', 'is_software_teacher']
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



# Compatibility imports retain existing integrations while implementations are layered.
from .services.time_data import (split_time_text, normalize_time_text, parse_time_entries,
    validate_schedule_time_text, find_unrecognized_time_entries)
from .schedule_views import ScheduleViewSet

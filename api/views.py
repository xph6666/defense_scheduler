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
from django.db.models import Count, Max, Q
from .schedule_integrity import schedule_write, audit, capture_export_groups, export_groups
from django.http import HttpResponse
from django.utils import timezone, translation
import json
from datetime import datetime, time
from .models import Group, OperationLog, Room, RuleConfig, ScheduleVersion, Student, Teacher
from .audit import AuditedDataMixin
from .permissions import IsAdminOrReadOnly, IsAdminUser, is_admin_user
from .timetable import CLASS_PERIOD_TIME_RANGES, TimetableParseError, extract_timetable_unavailable_times
from .services.import_time import DATE, combine_date_and_periods, normalize_text, supply_explicit_year
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
    '仅普通专家': 'expertOnly',
    '软件学院导师': 'isSoftwareTeacher',
    '是否软件学院导师': 'isSoftwareTeacher',
    '导师编号': 'mentorId',
    '秘书编号': 'secretaryId',
    '职称': 'title',
    '可担任角色': 'roles',
    '角色': 'roles',
    '校区偏好': 'campusPreference',
    '不可用时间': 'unavailableTimes',
    '可用时间已确认': 'availabilityConfirmed',
    '允许同组多名指导学生': 'allowMultipleStudents',
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
    'mentorId', 'secretaryId', 'expertOnly', 'expert_only',
    'availableTypes', 'available_types', 'campusPreference', 'campus_preference',
    'unavailableTimes', 'unavailable_times', 'avoidTeacherNames', 'avoid_teacher_names',
    'availabilityConfirmed', 'availability_confirmed', 'allowMultipleStudents', 'allow_multiple_students',
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
    if isinstance(value, time):
        return value.strftime('%H:%M:%S' if value.second else '%H:%M')
    if isinstance(value, datetime) and value.time() != time():
        return value.strftime('%Y-%m-%d %H:%M:%S' if value.second else '%Y-%m-%d %H:%M')
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
    normalized = header_aliases.get(text, text)
    for field in IMPORT_KNOWN_FIELDS:
        snake = ''.join('_' + char.lower() if char.isupper() else char for char in field).lstrip('_')
        if snake == normalized and any(char.isupper() for char in field):
            return field
    return normalized


def import_header_score(row, header_aliases):
    score = 0
    for index, value in enumerate(row):
        header = normalize_import_header(value, header_aliases, index)
        if header in IMPORT_KNOWN_FIELDS:
            score += 1
    return score


def read_import_dataframe(file, filename, header_aliases, sheet_name=None):
    import pandas as pd

    if filename.endswith('.csv'):
        raw = pd.read_csv(file, header=None)
        sheets = []
    elif filename.endswith(('.xls', '.xlsx')):
        book = pd.ExcelFile(file, engine_kwargs={'formatting_info': True} if filename.endswith('.xls') else {})
        sheets = book.sheet_names
        sheet_name = sheet_name or sheets[0]
        if sheet_name not in sheets:
            raise ValueError('所选工作表不存在，请重新选择')
        raw = pd.read_excel(book, sheet_name=sheet_name, header=None)
    else:
        raise ValueError('不支持的文件格式')

    if raw.empty:
        raw.attrs.update(sheets=sheets, sheet=sheet_name or '')
        return raw

    scores = [import_header_score(row, header_aliases) for row in raw.values[:10]]
    header_index = max(range(len(scores)), key=lambda index: scores[index])
    best_headers = [normalize_import_header(value, header_aliases, index)
                    for index, value in enumerate(raw.iloc[header_index].tolist())]
    has_header = scores[header_index] >= 2 or (
        scores[header_index] == 1 and any(key in best_headers for key in ('name', 'studentNo')))
    columns = [normalize_import_header(value, header_aliases, index)
               for index, value in enumerate(raw.iloc[header_index].tolist())] if has_header else [
                   f'__column_{index}' for index in range(len(raw.columns))]
    # Duplicate unknown headings must not discard cells when converting to records.
    columns = [name if name not in columns[:index] else f'__column_{index}'
               for index, name in enumerate(columns)]
    # Fill only actual vertical merges in supported resource fields. Blank cells
    # outside a merge must remain blank, rather than inherit another room/date.
    if has_header and filename.endswith(('.xls', '.xlsx')):
        if filename.endswith('.xlsx'):
            from openpyxl import load_workbook
            if hasattr(file, 'seek'):
                file.seek(0)
            workbook = load_workbook(file, data_only=True)
            merges = [(area.min_row - 1, area.max_row, area.min_col - 1, area.max_col)
                      for area in workbook[sheet_name].merged_cells.ranges]
            workbook.close()
        else:
            merges = book.book.sheet_by_name(sheet_name).merged_cells
        for first_row, last_row, first_col, last_col in merges:
            if (last_col - first_col == 1 and last_row - first_row > 1
                    and first_row > header_index and first_col < len(columns)
                    and columns[first_col] in ('name', 'campus', 'useDate', 'useTime', 'availableTimes')):
                raw.iloc[first_row:min(last_row, len(raw)), first_col] = raw.iloc[first_row, first_col]
    df = raw.iloc[header_index + 1 if has_header else 0:].copy()
    df.columns = columns
    df = df.dropna(how='all')
    df.attrs.update(sheets=sheets, sheet=sheet_name or '', has_header=has_header)
    return df


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

    text = normalize_text(text)
    room = re.match(r'(?P<room>\d+-\d+)\b', text)
    dates = re.search(DATE, text)
    if not room:
        return None
    if not dates:
        dates = re.search(r'\d{1,2}(?:月|/|-)\d{1,2}日?', text[room.end():])
        time_text = text[room.end():][dates.start():] if dates else '缺少借用日期或时间'
    else:
        time_text = text[dates.start():]
    campus = '创新港' if '创新港' in filename else '兴庆' if '兴庆' in filename else ''
    return {
        'campus': campus,
        'name': room.group('room'),
        'availableTimes': re.split(r'\s+服务[：:]?', time_text)[0].strip(),
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
            preview = str(request.data.get('preview', '')).lower() == 'true'
            import_year = request.data.get('importYear')
            if import_year:
                supply_explicit_year('1月1日', import_year)
            import_campus = request.data.get('campus', '')
            if import_campus and import_campus not in ('创新港', '兴庆'):
                return Response({'error': '请选择有效的校区'}, status=status.HTTP_400_BAD_REQUEST)
            header_aliases = self._get_import_header_aliases()
            try:
                df = read_import_dataframe(file, filename, header_aliases, request.data.get('sheetName'))
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            if df.empty:
                if preview:
                    return Response({'preview': True, 'canImport': False, 'rows': [],
                        'validCount': 0, 'invalidCount': 1, 'errorCount': 1,
                        'errors': [{'errors': {'non_field_errors': ['当前工作表为空，请选择其他工作表']}}],
                        'warnings': [], 'sheets': df.attrs.get('sheets', []),
                        'sheetName': df.attrs.get('sheet', '')})
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
            preview_rows = []

            batch_unique_values = {}
            prepared_rows = []

            for index, row in enumerate(data_list):
                row_number = int(df.index[index]) + 1
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

                    if isinstance(self, RoomViewSet) and not processed_row.get('campus') and import_campus:
                        processed_row['campus'] = import_campus
                    time_field = 'availableTimes' if isinstance(self, RoomViewSet) else 'unavailableTimes'
                    original_time = processed_row.get(time_field, '')
                    if processed_row.get('useDate'):
                        original_time = f"{processed_row['useDate']} {processed_row.get('useTime', '')}".strip()
                    processed_row['_importInputs'] = [{'row': row_number, 'time': str(original_time)}]

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
                        'memberEligible', 'member_eligible', 'isSoftwareTeacher', 'is_software_teacher', 'expertOnly', 'expert_only',
                        'availabilityConfirmed', 'availability_confirmed', 'allowMultipleStudents', 'allow_multiple_students']
                    for field in bool_fields:
                        if field in processed_row and isinstance(processed_row[field], str):
                            processed_row[field] = processed_row[field].lower() in ['true', '1', '是', 'yes']

                    prepared_rows.append((row_number, processed_row))
                except Exception as e:
                    errors.append({
                        'row': row_number,
                        'errors': {'non_field_errors': [str(e)]},
                    })

            prepared_rows = self.prepare_import_rows(prepared_rows, filename)

            for row_number, processed_row in prepared_rows:
                try:
                    row_errors = {}
                    time_field = 'availableTimes' if isinstance(self, RoomViewSet) else 'unavailableTimes'
                    raw_time = supply_explicit_year(processed_row.get(time_field, ''), import_year)
                    if isinstance(self, TeacherViewSet) and str(raw_time).strip():
                        processed_row.setdefault('availabilityConfirmed', True)
                    unrecognized = find_unrecognized_time_entries(raw_time)
                    if unrecognized:
                        row_errors[time_field] = [
                            f'无法识别时间：{entry}。请补齐年份并使用明确的日期和时段；未写入任何数据'
                            for entry in unrecognized
                        ]
                    valid_times, other_times = parse_time_entries(raw_time)
                    processed_row[time_field] = ','.join([
                        *valid_times, *(entry for entry in other_times if entry not in unrecognized),
                    ])
                    if isinstance(self, RoomViewSet):
                        for required in ('campus', 'name'):
                            if not processed_row.get(required):
                                row_errors[required] = ['请选择导入校区或在文件中补齐校区' if required == 'campus' else '未识别到教室名称，请检查表头或借用单格式']
                    inputs = processed_row.get('_importInputs', [{'row': row_number, 'time': ''}])
                    preview_rows.append({
                        'row': row_number, 'sheet': df.attrs.get('sheet', ''),
                        'sourceRows': [item['row'] for item in inputs],
                        'originalTime': '\n'.join(item['time'] for item in inputs),
                        'normalizedTime': processed_row.get(time_field, ''),
                        'values': {key: value for key, value in processed_row.items() if key in IMPORT_KNOWN_FIELDS},
                    })
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
                    with translation.override('zh-hans'):
                        valid = serializer.is_valid()
                    if valid:
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
                if preview:
                    return Response({
                        'preview': True, 'canImport': False, 'rows': preview_rows,
                        'validCount': len(valid_serializers), 'invalidCount': len(errors),
                        'errors': errors, 'errorCount': len(errors), 'warnings': warnings,
                        'sheets': df.attrs.get('sheets', []), 'sheetName': df.attrs.get('sheet', ''),
                    })
                return Response({
                    'message': '导入失败，请修正错误后重新导入。',
                    'errors': errors,
                    'errorCount': len(errors),
                }, status=status.HTTP_400_BAD_REQUEST)

            if not valid_serializers:
                return Response({'error': '未识别到可导入的数据，请检查文件类型、表头和工作表'}, status=status.HTTP_400_BAD_REQUEST)

            if preview:
                return Response({
                    'preview': True, 'canImport': True, 'rows': preview_rows,
                    'validCount': len(valid_serializers), 'invalidCount': 0,
                    'errors': [], 'errorCount': 0, 'warnings': warnings,
                    'sheets': df.attrs.get('sheets', []), 'sheetName': df.attrs.get('sheet', ''),
                })

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
            f'请修正后重新导入（{TIME_FORMAT_HINT}）'
        ]

    def prepare_import_row(self, processed_row, filename):
        from .services.reference_data import correct_imported_affiliation
        correct_imported_affiliation(processed_row)
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

    @action(detail=False, methods=['post'], url_path='batch-defense-types')
    def batch_defense_types(self, request):
        ids, types = request.data.get('ids'), request.data.get('defenseTypes')
        if (not isinstance(ids, list) or not ids or len(ids) > MAX_IMPORT_ROWS
                or any(type(pk) is not int or pk <= 0 for pk in ids)):
            return Response({'error': '请选择 1～1000 位学生'}, status=400)
        if (not isinstance(types, list) or not types
                or any(value not in DEFENSE_TYPE_LABELS.values() for value in types)):
            return Response({'error': '请选择有效的答辩环节'}, status=400)
        students = list(Student.objects.select_for_update().filter(pk__in=ids))
        if len(students) != len(set(ids)):
            return Response({'error': '部分学生已不存在，请刷新后重试'}, status=400)
        from .services.student_participation import nonparticipation_reason
        if any(nonparticipation_reason(student.remark) for student in students):
            return Response({'error': '所选学生含明确不参加本次答辩者；如已恢复参加，请先核对并更正其备注和校区'}, status=400)
        for student in students:
            student.defense_types = list(dict.fromkeys([*(student.defense_types or []), *types]))
        Student.objects.bulk_update(students, ['defense_types'])
        return Response({'message': f'已为 {len(students)} 位学生补充参与环节', 'count': len(students)})

    @action(detail=False, methods=['post'], url_path='import-cohort')
    def import_cohort(self, request):
        from .services.cohort_import import import_cohort
        from rest_framework.exceptions import ValidationError
        try:
            result = import_cohort(request)
            code = 400 if result.get('canImport') is False and not result.get('preview') else 200
            return Response(result, status=code)
        except (ValueError, ValidationError) as exc:
            return Response({'error': str(exc)}, status=400)
    import_header_aliases = {
        '参加答辩类型': 'defenseTypes',
        '参与环节': 'defenseTypes',
        '参与答辩类型': 'defenseTypes',
    }

    def get_serializer_context(self):
        context = super().get_serializer_context()
        raw_defense_type = self.request.query_params.get('defense_type')
        if not raw_defense_type:
            return context

        from rest_framework.exceptions import ValidationError

        labels_to_values = {label: value for value, label in DEFENSE_TYPE_LABELS.items()}
        defense_type = labels_to_values.get(raw_defense_type, raw_defense_type)
        if defense_type not in DEFENSE_TYPE_LABELS:
            raise ValidationError({'defense_type': '答辩类型必须为 pre、formal 或 mid'})

        versions = ScheduleVersion.objects.filter(defense_type=defense_type)
        if not is_admin_user(self.request.user):
            versions = versions.filter(status='published')
        version_id = self.request.query_params.get('version_id')
        if version_id:
            try:
                version_id = int(version_id)
            except (TypeError, ValueError):
                raise ValidationError({'version_id': '版本 ID 格式不正确'})
            version = versions.filter(pk=version_id).first()
            if version is None:
                raise ValidationError({'version_id': '所选答辩类型下不存在可查看的该版本'})
        elif is_admin_user(self.request.user):
            version = versions.filter(is_current=True).first()
        else:
            version = versions.order_by('-created_at').first()

        group_map = {}
        if version:
            memberships = {}
            for student_id, group_name in Group.objects.filter(
                schedule_version=version,
            ).values_list('students__id', 'group_id'):
                if student_id is not None:
                    memberships.setdefault(student_id, set()).add(group_name)
            group_map = {
                student_id: next(iter(group_names)) if len(group_names) == 1 else '多个分组'
                for student_id, group_names in memberships.items()
            }
        context['current_group_map'] = group_map
        return context

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

        from .services.student_participation import nonparticipation_reason
        if nonparticipation_reason(processed_row.get('remark')):
            processed_row['defenseTypes'] = []
            processed_row['campus'] = normalize_campus_text(processed_row.get('campus') or '')
            return processed_row

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

        explicit_types = getattr(self, 'request', None)
        explicit_types = explicit_types.data.get('defenseTypes') if explicit_types else None
        if explicit_types:
            try:
                explicit_types = json.loads(explicit_types) if isinstance(explicit_types, str) else explicit_types
            except (TypeError, ValueError):
                raise ValueError('补充参与环节格式不正确')
            if (not isinstance(explicit_types, list) or not explicit_types
                    or any(value not in DEFENSE_TYPE_LABELS.values() for value in explicit_types)):
                raise ValueError('请选择有效的补充参与环节')
            if not defense_types:
                defense_types = list(dict.fromkeys(explicit_types))
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
            f'请修正后重新导入（{TIME_FORMAT_HINT}）'
        ]

    def prepare_import_row(self, processed_row, filename):
        if not processed_row.get('name'):
            combined_text = ' '.join(dict.fromkeys(str(value) for value in processed_row.values() if value is not None))
            card_row = parse_card_style_room_text(combined_text, filename)
            if card_row:
                processed_row.update(card_row)
            if (not processed_row.get('name') and any(str(key).startswith('__column_') for key in processed_row)
                    and not any(key in IMPORT_KNOWN_FIELDS for key in processed_row)):
                return None

        if processed_row.get('campus'):
            processed_row['campus'] = normalize_campus_text(processed_row.get('campus'))
        elif '创新港' in filename or '兴庆' in filename:
            processed_row['campus'] = '创新港' if '创新港' in filename else '兴庆'

        if not processed_row.get('availableTimes') and (processed_row.get('useDate') or processed_row.get('useTime')):
            processed_row['availableTimes'] = combine_date_and_periods(processed_row.get('useDate', ''), processed_row.get('useTime', ''))

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
            existing_row.setdefault('_importInputs', []).extend(row.get('_importInputs', []))

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

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # 非管理员只能看到自己的操作，看不到服务端审计日志
        if not is_admin_user(request.user):
            queryset = queryset.filter(
                authoritative=False,
                operator=request.user.get_username()
            )

        include_authoritative = request.query_params.get('include_authoritative', 'true').lower()
        if include_authoritative == 'false':
            queryset = queryset.filter(authoritative=False)

        # 按模块筛选
        module = request.query_params.get('module')
        if module:
            queryset = queryset.filter(module=module)

        # 按操作类型筛选
        log_type = request.query_params.get('type')
        if log_type:
            queryset = queryset.filter(type=log_type)

        result = request.query_params.get('result')
        if result:
            queryset = queryset.filter(result=result)

        # 关键词搜索（描述、操作人）
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search)
                | Q(operator__icontains=search)
                | Q(type__icontains=search)
            )

        # 按日期范围筛选
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        # 分页：仅当显式传入 page 参数时才分页，否则返回完整列表（向后兼容）
        has_pagination = request.query_params.get('page') is not None
        if not has_pagination:
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        counts = queryset.aggregate(
            total=Count('id'),
            success=Count('id', filter=Q(result='成功')),
            failed=Count('id', filter=Q(result='失败')),
            audit=Count('id', filter=Q(authoritative=True)),
        )
        total = counts['total']
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 15))
        except (ValueError, TypeError):
            page = 1
            page_size = 15

        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 15

        start = (page - 1) * page_size
        end = start + page_size
        page_queryset = queryset[start:end]

        serializer = self.get_serializer(page_queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
            'stats': {
                'total': total,
                'success': counts['success'],
                'failed': counts['failed'],
                'audit': counts['audit'],
            },
        })



# Compatibility imports retain existing integrations while implementations are layered.
from .services.time_data import (split_time_text, normalize_time_text, parse_time_entries,
    validate_schedule_time_text, find_unrecognized_time_entries)
from .schedule_views import ScheduleViewSet

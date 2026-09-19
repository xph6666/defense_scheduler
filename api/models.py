from django.db import models

class Teacher(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="姓名")
    college = models.CharField(max_length=100, blank=True, verbose_name="所属学院")
    is_external = models.BooleanField(default=False, verbose_name="是否外院")
    title = models.CharField(max_length=20, verbose_name="职称")  # 教授/副教授/讲师
    roles = models.JSONField(default=list, verbose_name="可担任角色")
    available_types = models.JSONField(default=list, verbose_name="可参加答辩类型")
    campus_preference = models.CharField(max_length=20, blank=True, verbose_name="校区偏好")
    unavailable_times = models.TextField(blank=True, verbose_name="不可用时间")
    avoid_teacher_names = models.TextField(blank=True, verbose_name="不宜同组名单")
    remark = models.TextField(blank=True, verbose_name="备注")

    def __str__(self):
        return self.name

class Student(models.Model):
    name = models.CharField(max_length=50, verbose_name="姓名")
    student_no = models.CharField(max_length=30, unique=True, null=True, blank=True, verbose_name="学号")
    gender = models.CharField(max_length=10, blank=True, verbose_name="性别")
    student_type = models.CharField(max_length=20, default="学硕", verbose_name="学生类型")
    mentor_name = models.CharField(max_length=50, blank=True, verbose_name="导师姓名")
    campus = models.CharField(max_length=20, default="创新港", verbose_name="所属校区")
    defense_types = models.JSONField(default=list, verbose_name="参加答辩类型")
    secretary_name = models.CharField(max_length=50, blank=True, verbose_name="对应秘书姓名")
    remark = models.TextField(blank=True, verbose_name="备注")

    def __str__(self):
        return self.name

class Room(models.Model):
    campus = models.CharField(max_length=20, default="创新港", verbose_name="校区")
    name = models.CharField(max_length=50, default="", verbose_name="教室名称")
    capacity = models.IntegerField(default=30, verbose_name="容纳人数")
    available_times = models.TextField(blank=True, verbose_name="可用时间段")
    remark = models.TextField(blank=True, verbose_name="备注")

    def __str__(self):
        return f"{self.campus} - {self.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['campus', 'name'], name='unique_room_campus_name'),
        ]


class ScheduleVersion(models.Model):
    """排期版本，每次生成保存为一个版本"""
    DEFENSE_TYPE_CHOICES = [
        ('pre', '预答辩'),
        ('formal', '正式答辩'),
        ('mid', '中期答辩'),
    ]
    version = models.IntegerField(default=1, verbose_name="版本号")
    defense_type = models.CharField(max_length=10, choices=DEFENSE_TYPE_CHOICES, verbose_name="答辩类型")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    is_current = models.BooleanField(default=True, verbose_name="是否当前生效")
    rules_snapshot = models.JSONField(default=dict, verbose_name="规则快照")
    conflicts_snapshot = models.JSONField(default=list, blank=True, verbose_name="生成时冲突快照")
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, default='draft', choices=[('draft', '草稿'), ('published', '已发布')])
    published_at = models.DateTimeField(null=True, blank=True)
    result_snapshot = models.JSONField(default=dict, blank=True)
    export_snapshot = models.JSONField(default=list, blank=True)
    input_snapshot = models.JSONField(default=dict, blank=True)
    request_key = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['defense_type', 'version'], name='unique_schedule_version'),
            models.UniqueConstraint(fields=['defense_type'], condition=models.Q(is_current=True), name='unique_current_schedule'),
        ]

    def __str__(self):
        return f"{self.defense_type} v{self.version} - {self.created_at}"

class Group(models.Model):
    """分组详情"""
    schedule_version = models.ForeignKey(ScheduleVersion, on_delete=models.CASCADE, related_name='groups')
    group_id = models.CharField(max_length=20, verbose_name="组编号")
    time = models.CharField(max_length=50, verbose_name="时间段")
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, verbose_name="教室")
    campus = models.CharField(max_length=20, verbose_name="校区")
    chair = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, related_name='chair_groups', verbose_name="主席/组长")
    experts = models.ManyToManyField(Teacher, related_name='expert_groups', verbose_name="专家列表")
    secretary = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, related_name='secretary_groups', verbose_name="秘书")
    students = models.ManyToManyField('Student', related_name='groups', verbose_name="学生列表")

    def __str__(self):
        return self.group_id


class RuleConfig(models.Model):
    """规则配置，每种答辩类型一条记录"""
    defense_type = models.CharField(max_length=10, unique=True, verbose_name="答辩类型")
    config = models.JSONField(default=dict, verbose_name="配置内容")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def __str__(self):
        return f"规则配置 - {self.defense_type}"


class OperationLog(models.Model):
    """操作日志"""
    type = models.CharField(max_length=30, verbose_name="操作类型")
    module = models.CharField(max_length=50, verbose_name="模块")
    description = models.TextField(verbose_name="描述")
    operator = models.CharField(max_length=50, default='系统', verbose_name="操作人")
    result = models.CharField(max_length=10, default='成功', verbose_name="结果")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    details = models.JSONField(default=dict, blank=True)
    authoritative = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.type} - {self.description[:20]}"


class ScheduleWriteLock(models.Model):
    """A database-backed mutex; acquired before reading schedule mutation state."""
    revision = models.PositiveBigIntegerField(default=0)

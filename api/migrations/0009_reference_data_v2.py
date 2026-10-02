from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion


def upgrade_reference_data(apps, schema_editor):
    alias = schema_editor.connection.alias
    Teacher = apps.get_model('api', 'Teacher')
    Student = apps.get_model('api', 'Student')
    RuleConfig = apps.get_model('api', 'RuleConfig')
    # An ambiguous whitespace-normalized name must remain unresolved.
    teachers = {}
    exact_teachers = {}
    ambiguous = set()
    for teacher in Teacher.objects.using(alias).all().iterator():
        exact_teachers[teacher.name] = teacher
        name = teacher.name.strip()
        if name in teachers:
            ambiguous.add(name)
        teachers[name] = teacher
    for name in ambiguous:
        teachers.pop(name, None)
    for student in Student.objects.using(alias).all().iterator():
        changed = []
        for relation, name_field in (('mentor', 'mentor_name'), ('bound_secretary', 'secretary_name')):
            name = getattr(student, name_field) or ''
            teacher = exact_teachers.get(name) or teachers.get(name.strip())
            if teacher:
                setattr(student, relation + '_id', teacher.pk)
                setattr(student, name_field, teacher.name)
                changed.extend([relation, name_field])
        if changed:
            student.save(using=alias, update_fields=changed)
    today = timezone.localdate()
    for rules in RuleConfig.objects.using(alias).all().iterator():
        if rules.defense_type not in ('pre', 'formal', 'mid'):
            continue
        config = dict(rules.config or {})
        config['policyVersion'] = 2
        config['expertCountIncludesChair'] = True
        config['courseHalfDayBlocking'] = True
        config['secretaryCount'] = 1
        config.setdefault('includeRemarks', True)
        config.setdefault('preservePreDefenseGroups', True)
        config.setdefault('formalSoftwareMin', 3)
        if rules.defense_type != 'formal':
            config['mentorAvoidance'] = False
        else:
            config.setdefault('mentorAvoidance', True)
        old_students = config.get('studentCount')
        if not old_students or old_students == {'target': 5, 'min': 3, 'max': 8}:
            config['studentCount'] = ({'target': 12, 'min': 10, 'max': 13} if rules.defense_type == 'mid'
                                      else {'target': 6, 'min': 4, 'max': 8})
        experts = dict(config.get('expertCount') or {})
        floor = 4 if rules.defense_type == 'pre' else 5
        if rules.defense_type == 'formal':
            experts.update(target=5, min=5, max=5)
        else:
            for key in ('min', 'target'):
                try:
                    experts[key] = max(int(experts.get(key, floor)), floor)
                except (TypeError, ValueError):
                    experts[key] = floor
            experts['target'] = max(experts['target'], experts['min'])
        experts['includesChair'] = True
        config['expertCount'] = experts
        old_default_dates = config.get('startDate') == '2025-05-10' and config.get('endDate') == '2025-05-20'
        if not config.get('startDate') or old_default_dates:
            config['startDate'] = today.isoformat()
        if not config.get('endDate') or old_default_dates:
            config['endDate'] = (today + timedelta(days=10)).isoformat()
        qualifications = {'leaderMinTitle': '副教授', 'chairmanMinTitle': '教授',
                          'secretaryMinTitle': '讲师', 'preferSeniorTitle': True}
        qualifications.update(config.get('roleQualification') or {})
        config['roleQualification'] = qualifications
        rules.config = config
        rules.save(using=alias, update_fields=['config'])


class Migration(migrations.Migration):
    dependencies = [('api', '0008_schedule_stability')]

    operations = [
        migrations.AddField(model_name='teacher', name='is_active',
            field=models.BooleanField(default=True, verbose_name='是否启用')),
        migrations.AddField(model_name='teacher', name='member_eligible',
            field=models.BooleanField(default=True, verbose_name='是否可担任普通专家')),
        migrations.AddField(model_name='teacher', name='is_software_teacher',
            field=models.BooleanField(default=False, verbose_name='是否软件学院导师')),
        migrations.AddField(model_name='student', name='mentor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='mentored_students', to='api.teacher', verbose_name='导师')),
        migrations.AddField(model_name='student', name='bound_secretary',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='bound_students', to='api.teacher', verbose_name='对应秘书')),
        migrations.AddField(model_name='scheduleversion', name='source_pre_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='linked_formal_versions', to='api.scheduleversion', verbose_name='沿用的预答辩版本')),
        migrations.RunPython(upgrade_reference_data, migrations.RunPython.noop),
    ]

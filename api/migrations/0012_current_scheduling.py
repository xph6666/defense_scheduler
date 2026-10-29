from django.db import migrations, models


def correct_affiliations(apps, schema_editor):
    Teacher = apps.get_model('api', 'Teacher')
    Teacher.objects.filter(name__in=['王飞（软）', '王飞(软)']).update(is_external=False, is_software_teacher=True, college='软件学院')
    Teacher.objects.filter(name='王飞').update(is_external=True, is_software_teacher=False)
    Teacher.objects.filter(name='王飞', college='软件学院').update(college='外院（学院待确认）')


class Migration(migrations.Migration):
    dependencies = [('api', '0011_teacher_expert_only')]
    operations = [
        migrations.AddField('teacher', 'available_times', models.TextField(blank=True, verbose_name='可用时间')),
        migrations.AddField('teacher', 'availability_confirmed', models.BooleanField(default=False, verbose_name='可用时间已确认')),
        migrations.AddField('teacher', 'allow_multiple_students', models.BooleanField(default=False, verbose_name='允许同组多名指导学生')),
        migrations.RunPython(correct_affiliations, migrations.RunPython.noop),
    ]

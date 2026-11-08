from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('api', '0012_current_scheduling')]
    operations = [
        migrations.RemoveConstraint(model_name='scheduleversion', name='unique_current_schedule'),
        migrations.AddField(model_name='scheduleversion', name='campus_scope',
                            field=models.CharField(blank=True, default='', max_length=20, verbose_name='排期校区批次')),
        migrations.AddConstraint(model_name='scheduleversion', constraint=models.UniqueConstraint(
            fields=('defense_type', 'campus_scope'), condition=models.Q(is_current=True), name='unique_current_schedule')),
    ]

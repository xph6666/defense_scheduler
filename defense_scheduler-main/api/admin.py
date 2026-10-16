from django.contrib import admin
from django import forms
from .models import Teacher, Student, Room
from .services.reference_data import ReferenceDataError, sync_student_references, sync_teacher_rename


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'title', 'is_active', 'member_eligible', 'is_software_teacher')
    list_filter = ('is_active', 'member_eligible', 'is_software_teacher', 'college', 'title')
    search_fields = ('name', 'college')

    def save_model(self, request, obj, form, change):
        previous_name = Teacher.objects.get(pk=obj.pk).name if change else obj.name
        super().save_model(request, obj, form, change)
        sync_teacher_rename(obj, previous_name)


class StudentReferenceForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        fields = ('mentor', 'mentor_name', 'bound_secretary', 'secretary_name')
        attrs = {key: cleaned[key] for key in fields if key in cleaned and key in self.changed_data}
        try:
            cleaned.update(sync_student_references(attrs, self.instance))
        except ReferenceDataError as exc:
            labels = {'mentorName': 'mentor_name', 'secretaryName': 'secretary_name'}
            for key, messages in exc.errors.items():
                self.add_error(labels.get(key, key), messages)
        return cleaned


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentReferenceForm
    list_display = ('name', 'student_no', 'student_type', 'mentor', 'bound_secretary', 'campus')
    list_filter = ('student_type', 'campus')
    search_fields = ('name', 'student_no', 'mentor_name', 'mentor__name', 'secretary_name', 'bound_secretary__name')
    list_select_related = ('mentor', 'bound_secretary')


admin.site.register(Room)

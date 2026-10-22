from django.contrib import admin

from .models import Doctor, DoctorWorkingHour


class DoctorWorkingHourInline(admin.TabularInline):
    model = DoctorWorkingHour
    extra = 0


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['name', 'specialization', 'is_active']
    list_filter = ['is_active', 'specialization']
    inlines = [DoctorWorkingHourInline]

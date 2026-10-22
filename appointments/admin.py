from django.contrib import admin

from .models import Appointment, Patient
from .services import SLOT_DURATION


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'created_at']
    search_fields = ['name', 'email']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['starts_at', 'doctor', 'patient', 'status']
    list_filter = ['status', 'doctor']
    list_select_related = ['doctor', 'patient']
    # Appointments are always 30 minutes, so only the start is entered.
    readonly_fields = ['ends_at', 'created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        obj.ends_at = obj.starts_at + SLOT_DURATION
        super().save_model(request, obj, form, change)

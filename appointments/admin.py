from django.contrib import admin

from .models import Appointment, Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'created_at']
    search_fields = ['name', 'email']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['starts_at', 'doctor', 'patient', 'status']
    list_filter = ['status', 'doctor']
    list_select_related = ['doctor', 'patient']

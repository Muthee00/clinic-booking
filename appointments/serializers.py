from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from doctors.models import Doctor

from .models import Appointment, Patient


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ['id', 'name', 'email', 'created_at']
        read_only_fields = ['id', 'created_at']


class AppointmentSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    date = serializers.SerializerMethodField(help_text='YYYY-MM-DD in clinic time.')
    start_time = serializers.SerializerMethodField(help_text='HH:MM in clinic time.')
    end_time = serializers.SerializerMethodField(help_text='HH:MM in clinic time.')

    class Meta:
        model = Appointment
        fields = [
            'id', 'doctor', 'doctor_name', 'patient', 'patient_name', 'date', 'start_time', 'end_time',
            'starts_at', 'ends_at', 'status', 'cancellation_reason', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_date(self, obj) -> str:
        return timezone.localtime(obj.starts_at).date().isoformat()

    def get_start_time(self, obj) -> str:
        return f'{timezone.localtime(obj.starts_at):%H:%M}'

    def get_end_time(self, obj) -> str:
        return f'{timezone.localtime(obj.ends_at):%H:%M}'


class SlotInputSerializer(serializers.Serializer):
    """Accepts a slot either as `date` + `time` (clinic local time) or as a full `starts_at`."""

    date = serializers.DateField(required=False, help_text='YYYY-MM-DD, e.g. 2026-10-23.')
    time = serializers.TimeField(required=False, help_text='HH:MM in clinic time, e.g. 09:00 or 14:30.')
    starts_at = serializers.DateTimeField(
        required=False,
        help_text='Alternative to date + time: ISO 8601, e.g. 2026-10-23T09:00:00+03:00. '
        'Values without an offset use the clinic timezone.',
    )

    def validate(self, attrs):
        date, time = attrs.pop('date', None), attrs.pop('time', None)
        if 'starts_at' in attrs:
            if date or time:
                raise serializers.ValidationError('Send either `date` + `time` or `starts_at`, not both.')
            return attrs
        if not (date and time):
            raise serializers.ValidationError('Send `date` and `time` (or a full `starts_at`).')
        attrs['starts_at'] = timezone.make_aware(datetime.combine(date, time))
        return attrs


class AppointmentCreateSerializer(SlotInputSerializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())


class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class AppointmentRescheduleSerializer(SlotInputSerializer):
    pass

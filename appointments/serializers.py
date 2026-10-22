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

    class Meta:
        model = Appointment
        fields = [
            'id', 'doctor', 'doctor_name', 'patient', 'patient_name', 'starts_at', 'ends_at',
            'status', 'cancellation_reason', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AppointmentCreateSerializer(serializers.Serializer):
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.all())
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    starts_at = serializers.DateTimeField(
        help_text='ISO 8601. Must fall on a :00 or :30 boundary. Naive values use the clinic timezone.'
    )


class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class AppointmentRescheduleSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField(help_text='New slot start, same rules as booking.')

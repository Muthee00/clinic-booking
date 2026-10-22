from rest_framework import serializers

from .models import Doctor, DoctorWorkingHour


class DoctorWorkingHourSerializer(serializers.ModelSerializer):
    weekday_name = serializers.CharField(source='get_weekday_display', read_only=True)

    class Meta:
        model = DoctorWorkingHour
        fields = ['weekday', 'weekday_name', 'start_time', 'end_time']


class DoctorSerializer(serializers.ModelSerializer):
    working_hours = DoctorWorkingHourSerializer(many=True, read_only=True)

    class Meta:
        model = Doctor
        fields = ['id', 'name', 'specialization', 'is_active', 'working_hours']


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField(help_text='YYYY-MM-DD, in the clinic timezone.')


class SlotSerializer(serializers.Serializer):
    time = serializers.CharField(help_text='HH:MM in clinic time; send this with `date` to book.')
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class AvailabilitySerializer(serializers.Serializer):
    doctor = serializers.IntegerField()
    date = serializers.DateField()
    timezone = serializers.CharField()
    slot_minutes = serializers.IntegerField()
    slots = SlotSerializer(many=True)

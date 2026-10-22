from django.db import models
from django.db.models import F, Q


class Doctor(models.Model):
    name = models.CharField(max_length=120)
    specialization = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.specialization})'


class DoctorWorkingHour(models.Model):
    """A block of time on a weekday when the doctor sees patients (clinic local time)."""

    class Weekday(models.IntegerChoices):
        # Matches Python's date.weekday().
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='working_hours')
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ['doctor', 'weekday', 'start_time']
        constraints = [
            models.CheckConstraint(
                condition=Q(start_time__lt=F('end_time')),
                name='working_hour_start_before_end',
            ),
            models.UniqueConstraint(
                fields=['doctor', 'weekday', 'start_time'],
                name='unique_working_hour_block',
            ),
        ]

    def __str__(self):
        return f'{self.doctor.name}: {self.get_weekday_display()} {self.start_time}-{self.end_time}'

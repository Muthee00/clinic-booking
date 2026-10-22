from django.db import models
from django.db.models import F, Q

from doctors.models import Doctor


class Patient(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} <{self.email}>'


class Appointment(models.Model):
    class Status(models.TextChoices):
        BOOKED = 'booked', 'Booked'
        CANCELLED = 'cancelled', 'Cancelled'

    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='appointments')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at']
        indexes = [models.Index(fields=['patient', 'status', 'starts_at'])]
        constraints = [
            # Slots are fixed 30-minute blocks on a 30-minute grid, so a unique start
            # per doctor among active appointments is equivalent to "no overlap".
            # Partial unique indexes are supported by both PostgreSQL and SQLite.
            models.UniqueConstraint(
                fields=['doctor', 'starts_at'],
                condition=Q(status='booked'),
                name='unique_active_doctor_slot',
            ),
            models.UniqueConstraint(
                fields=['patient', 'starts_at'],
                condition=Q(status='booked'),
                name='unique_active_patient_slot',
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F('starts_at')),
                name='appointment_ends_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.patient.name} with {self.doctor.name} at {self.starts_at:%Y-%m-%d %H:%M}'

from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from appointments.models import Patient
from doctors.models import Doctor, DoctorWorkingHour

WEEKDAYS = range(0, 5)  # Monday-Friday

# (name, specialization, [(weekdays, start, end), ...])
DOCTORS = [
    ('Dr. Amina Odhiambo', 'General Practice', [(WEEKDAYS, time(8, 0), time(17, 0))]),
    ('Dr. Brian Kamau', 'Pediatrics', [(WEEKDAYS, time(9, 0), time(13, 0)), (WEEKDAYS, time(14, 0), time(17, 0))]),
    ('Dr. Cynthia Wanjiru', 'Dermatology', [((0, 2, 4), time(10, 0), time(16, 0))]),
    ('Dr. David Otieno', 'Cardiology', [((1, 3), time(8, 0), time(14, 0)), ((5,), time(9, 0), time(12, 0))]),
    ('Dr. Esther Mutua', 'Dentistry', [(WEEKDAYS, time(9, 0), time(18, 0))]),
]

PATIENTS = [
    ('Demo Patient One', 'patient.one@example.com'),
    ('Demo Patient Two', 'patient.two@example.com'),
]


class Command(BaseCommand):
    help = 'Seed five doctors with weekly working hours and two demo patients. Safe to run repeatedly.'

    @transaction.atomic
    def handle(self, *args, **options):
        for name, specialization, schedule in DOCTORS:
            doctor, _ = Doctor.objects.update_or_create(
                name=name, defaults={'specialization': specialization, 'is_active': True}
            )
            doctor.working_hours.all().delete()
            DoctorWorkingHour.objects.bulk_create(
                DoctorWorkingHour(doctor=doctor, weekday=day, start_time=start, end_time=end)
                for days, start, end in schedule
                for day in days
            )
            self.stdout.write(f'Seeded {doctor} (id={doctor.pk})')

        for name, email in PATIENTS:
            patient, _ = Patient.objects.get_or_create(email=email, defaults={'name': name})
            self.stdout.write(f'Seeded {patient} (id={patient.pk})')

        self.stdout.write(self.style.SUCCESS('Seed data ready.'))

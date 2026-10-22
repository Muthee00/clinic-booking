from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from appointments.models import Appointment, Patient

from .models import Doctor, DoctorWorkingHour


class AvailabilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name='Dr. Test', specialization='General Practice')
        self.day = timezone.localdate() + timedelta(days=2)
        DoctorWorkingHour.objects.create(
            doctor=self.doctor, weekday=self.day.weekday(), start_time=time(9), end_time=time(11)
        )
        self.url = reverse('doctor-availability', args=[self.doctor.pk])

    def test_returns_30_minute_slots_excluding_booked(self):
        booked = timezone.make_aware(datetime.combine(self.day, time(9, 30)))
        Appointment.objects.create(
            doctor=self.doctor,
            patient=Patient.objects.create(name='Jane', email='jane@example.com'),
            starts_at=booked,
            ends_at=booked + timedelta(minutes=30),
        )

        response = self.client.get(self.url, {'date': self.day.isoformat()})

        self.assertEqual(response.status_code, 200)
        times = [datetime.fromisoformat(s['starts_at']).strftime('%H:%M') for s in response.data['slots']]
        self.assertEqual(times, ['09:00', '10:00', '10:30'])
        self.assertEqual(response.data['timezone'], 'Africa/Nairobi')

    def test_day_off_returns_no_slots(self):
        response = self.client.get(self.url, {'date': (self.day + timedelta(days=1)).isoformat()})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['slots'], [])

    def test_date_is_required_and_validated(self):
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertEqual(self.client.get(self.url, {'date': '2026-13-40'}).status_code, 400)

    def test_unknown_doctor_returns_404(self):
        url = reverse('doctor-availability', args=[9999])
        self.assertEqual(self.client.get(url, {'date': self.day.isoformat()}).status_code, 404)

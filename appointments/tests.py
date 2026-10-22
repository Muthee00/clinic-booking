from datetime import datetime, time, timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from doctors.models import Doctor, DoctorWorkingHour

from .models import Appointment, Patient


def local_dt(date, hour, minute=0):
    return timezone.make_aware(datetime.combine(date, time(hour, minute)))


class BookingTestCase(TestCase):
    """Doctor works 08:00-17:00 every day so tests do not depend on today's weekday."""

    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(name='Dr. Test', specialization='General Practice')
        DoctorWorkingHour.objects.bulk_create(
            DoctorWorkingHour(doctor=self.doctor, weekday=day, start_time=time(8), end_time=time(17))
            for day in range(7)
        )
        self.patient = Patient.objects.create(name='Jane Doe', email='jane@example.com')
        self.other_patient = Patient.objects.create(name='John Roe', email='john@example.com')
        self.day = timezone.localdate() + timedelta(days=2)
        self.slot = local_dt(self.day, 10)

    def book(self, starts_at, patient=None, doctor=None):
        return self.client.post(
            reverse('appointment-create'),
            {
                'doctor': (doctor or self.doctor).pk,
                'patient': (patient or self.patient).pk,
                'starts_at': starts_at.isoformat(),
            },
            format='json',
        )

    def cancel(self, appointment_id, reason='Feeling better'):
        return self.client.patch(
            reverse('appointment-cancel', args=[appointment_id]), {'cancellation_reason': reason}, format='json'
        )

    def reschedule(self, appointment_id, starts_at):
        return self.client.patch(
            reverse('appointment-reschedule', args=[appointment_id]),
            {'starts_at': starts_at.isoformat()},
            format='json',
        )

    def available_starts(self, date=None):
        response = self.client.get(
            reverse('doctor-availability', args=[self.doctor.pk]), {'date': (date or self.day).isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        return [datetime.fromisoformat(s['starts_at']) for s in response.data['slots']]


class BookAppointmentTests(BookingTestCase):
    def test_successful_booking(self):
        response = self.book(self.slot)

        self.assertEqual(response.status_code, 201, response.data)
        appointment = Appointment.objects.get(pk=response.data['id'])
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)
        self.assertEqual(appointment.starts_at, self.slot)
        self.assertEqual(appointment.ends_at - appointment.starts_at, timedelta(minutes=30))

    def test_duplicate_booking_is_rejected(self):
        self.assertEqual(self.book(self.slot).status_code, 201)

        response = self.book(self.slot, patient=self.other_patient)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'slot_unavailable')
        self.assertEqual(Appointment.objects.count(), 1)

    def test_patient_cannot_double_book_across_doctors(self):
        other_doctor = Doctor.objects.create(name='Dr. Other', specialization='Dentistry')
        DoctorWorkingHour.objects.create(
            doctor=other_doctor, weekday=self.day.weekday(), start_time=time(8), end_time=time(17)
        )
        self.assertEqual(self.book(self.slot).status_code, 201)

        response = self.book(self.slot, doctor=other_doctor)

        self.assertEqual(response.status_code, 409)

    def test_outside_working_hours_is_rejected(self):
        response = self.book(local_dt(self.day, 17))  # would end 17:30, after closing

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'outside_working_hours')

    def test_day_without_working_hours_is_rejected(self):
        self.doctor.working_hours.filter(weekday=self.day.weekday()).delete()

        response = self.book(self.slot)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'outside_working_hours')

    def test_misaligned_slot_is_rejected(self):
        response = self.book(local_dt(self.day, 10, 15))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'misaligned_slot')

    def test_past_appointment_is_rejected(self):
        response = self.book(local_dt(timezone.localdate() - timedelta(days=1), 10))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'past_slot')

    def test_booking_within_one_hour_is_rejected(self):
        with mock.patch('django.utils.timezone.now', return_value=local_dt(self.day, 9, 15)):
            too_soon = self.book(local_dt(self.day, 10))
            allowed = self.book(local_dt(self.day, 10, 30))

        self.assertEqual(too_soon.status_code, 400)
        self.assertEqual(too_soon.data['code'], 'insufficient_notice')
        self.assertEqual(allowed.status_code, 201)

    def test_inactive_doctor_is_rejected(self):
        self.doctor.is_active = False
        self.doctor.save()

        response = self.book(self.slot)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'doctor_inactive')

    def test_unknown_doctor_returns_validation_error(self):
        response = self.client.post(
            reverse('appointment-create'),
            {'doctor': 9999, 'patient': self.patient.pk, 'starts_at': self.slot.isoformat()},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('doctor', response.data)

    def test_database_rejects_duplicate_active_booking(self):
        Appointment.objects.create(
            doctor=self.doctor, patient=self.patient, starts_at=self.slot, ends_at=self.slot + timedelta(minutes=30)
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                doctor=self.doctor,
                patient=self.other_patient,
                starts_at=self.slot,
                ends_at=self.slot + timedelta(minutes=30),
            )


class CancelAppointmentTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        self.appointment_id = self.book(self.slot).data['id']

    def test_cancellation_preserves_record(self):
        response = self.cancel(self.appointment_id, '  Travelling  ')

        self.assertEqual(response.status_code, 200, response.data)
        appointment = Appointment.objects.get(pk=self.appointment_id)
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(appointment.cancellation_reason, 'Travelling')

    def test_cancellation_requires_reason(self):
        for body in ({}, {'cancellation_reason': '   '}):
            response = self.client.patch(
                reverse('appointment-cancel', args=[self.appointment_id]), body, format='json'
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Appointment.objects.get(pk=self.appointment_id).status, Appointment.Status.BOOKED)

    def test_repeated_cancellation_is_rejected(self):
        self.assertEqual(self.cancel(self.appointment_id).status_code, 200)

        response = self.cancel(self.appointment_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'already_cancelled')

    def test_cancelled_slot_is_released(self):
        self.assertNotIn(self.slot, self.available_starts())

        self.cancel(self.appointment_id)

        self.assertIn(self.slot, self.available_starts())
        rebook = self.book(self.slot, patient=self.other_patient)
        self.assertEqual(rebook.status_code, 201, rebook.data)

    def test_cancel_unknown_appointment_returns_404(self):
        self.assertEqual(self.cancel(9999).status_code, 404)


class RescheduleAppointmentTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        self.appointment_id = self.book(self.slot).data['id']
        self.new_slot = local_dt(self.day, 11)

    def assert_unchanged(self):
        appointment = Appointment.objects.get(pk=self.appointment_id)
        self.assertEqual(appointment.starts_at, self.slot)
        self.assertEqual(appointment.ends_at, self.slot + timedelta(minutes=30))
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)

    def test_successful_reschedule(self):
        response = self.reschedule(self.appointment_id, self.new_slot)

        self.assertEqual(response.status_code, 200, response.data)
        appointment = Appointment.objects.get(pk=self.appointment_id)
        self.assertEqual(appointment.starts_at, self.new_slot)
        self.assertEqual(appointment.ends_at, self.new_slot + timedelta(minutes=30))
        self.assertIn(self.slot, self.available_starts())
        self.assertNotIn(self.new_slot, self.available_starts())

    def test_reschedule_to_occupied_slot_preserves_original(self):
        self.book(self.new_slot, patient=self.other_patient)

        response = self.reschedule(self.appointment_id, self.new_slot)

        self.assertEqual(response.status_code, 409)
        self.assert_unchanged()

    def test_reschedule_to_invalid_slot_preserves_original(self):
        for bad_slot, code in [
            (local_dt(self.day, 20), 'outside_working_hours'),
            (local_dt(self.day, 11, 10), 'misaligned_slot'),
            (local_dt(timezone.localdate() - timedelta(days=1), 10), 'past_slot'),
        ]:
            response = self.reschedule(self.appointment_id, bad_slot)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['code'], code)
        self.assert_unchanged()

    def test_reschedule_cancelled_appointment_is_rejected(self):
        self.cancel(self.appointment_id)

        response = self.reschedule(self.appointment_id, self.new_slot)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'cancelled_appointment')
        appointment = Appointment.objects.get(pk=self.appointment_id)
        self.assertEqual(appointment.starts_at, self.slot)


class PatientAppointmentsTests(BookingTestCase):
    def test_lists_upcoming_active_appointments_in_start_order(self):
        later = self.book(local_dt(self.day, 15)).data['id']
        earlier = self.book(local_dt(self.day, 9)).data['id']
        middle = self.book(self.slot).data['id']
        cancelled = self.book(local_dt(self.day, 12)).data['id']
        self.cancel(cancelled)
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            starts_at=local_dt(self.day - timedelta(days=5), 10),
            ends_at=local_dt(self.day - timedelta(days=5), 10, 30),
        )
        self.book(local_dt(self.day, 13), patient=self.other_patient)

        response = self.client.get(reverse('patient-appointments', args=[self.patient.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([a['id'] for a in response.data], [earlier, middle, later])

    def test_unknown_patient_returns_404(self):
        self.assertEqual(self.client.get(reverse('patient-appointments', args=[9999])).status_code, 404)


class SchemaTests(TestCase):
    def test_openapi_schema_and_docs_render(self):
        self.assertEqual(self.client.get(reverse('schema')).status_code, 200)
        self.assertEqual(self.client.get(reverse('swagger-ui')).status_code, 200)

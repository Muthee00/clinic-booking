"""Booking business rules.

Views stay thin and call into this module. Every write runs inside
`transaction.atomic()` and takes row locks (`select_for_update`) so concurrent
requests for the same doctor are serialised on PostgreSQL. The partial unique
constraints on `Appointment` are the final guard: if two writers still race,
the database rejects the second and we report a 409.
"""

from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from doctors.models import Doctor

from .exceptions import BookingError, InvalidAppointmentState, SlotUnavailable
from .models import Appointment, Patient

SLOT_MINUTES = 30
SLOT_DURATION = timedelta(minutes=SLOT_MINUTES)
MIN_BOOKING_NOTICE = timedelta(hours=1)


def _ensure_aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value)  # interpreted in settings.TIME_ZONE
    return value


def _is_within_working_hours(doctor, local_start):
    local_end = local_start + SLOT_DURATION
    if local_end.date() != local_start.date():
        return False
    return doctor.working_hours.filter(
        weekday=local_start.weekday(),
        start_time__lte=local_start.time(),
        end_time__gte=local_end.time(),
    ).exists()


def validate_slot(doctor, patient, starts_at, exclude_appointment_id=None):
    """Raise a BookingError subclass if `starts_at` cannot be booked."""
    if not doctor.is_active:
        raise BookingError('This doctor is not currently accepting appointments.', code='doctor_inactive')

    local_start = timezone.localtime(starts_at)
    if local_start.minute % SLOT_MINUTES or local_start.second or local_start.microsecond:
        raise BookingError(
            'Appointments must start on a 30-minute boundary (e.g. 09:00 or 09:30).',
            code='misaligned_slot',
        )

    now = timezone.now()
    if starts_at <= now:
        raise BookingError('Appointments cannot be booked in the past.', code='past_slot')
    if starts_at < now + MIN_BOOKING_NOTICE:
        raise BookingError('Appointments must be booked at least 1 hour in advance.', code='insufficient_notice')

    if not _is_within_working_hours(doctor, local_start):
        raise BookingError("The requested slot is outside the doctor's working hours.", code='outside_working_hours')

    overlapping = Appointment.objects.filter(
        status=Appointment.Status.BOOKED,
        starts_at__lt=starts_at + SLOT_DURATION,
        ends_at__gt=starts_at,
    )
    if exclude_appointment_id is not None:
        overlapping = overlapping.exclude(pk=exclude_appointment_id)
    if overlapping.filter(doctor=doctor).exists():
        raise SlotUnavailable('This slot is already booked for the doctor.')
    if overlapping.filter(patient=patient).exists():
        raise SlotUnavailable('The patient already has an appointment at this time.')


def book_appointment(*, doctor: Doctor, patient: Patient, starts_at: datetime) -> Appointment:
    starts_at = _ensure_aware(starts_at)
    try:
        with transaction.atomic():
            # Lock the doctor row so concurrent bookings for this doctor queue up.
            doctor = Doctor.objects.select_for_update().get(pk=doctor.pk)
            validate_slot(doctor, patient, starts_at)
            return Appointment.objects.create(
                doctor=doctor,
                patient=patient,
                starts_at=starts_at,
                ends_at=starts_at + SLOT_DURATION,
            )
    except IntegrityError:
        raise SlotUnavailable()


def cancel_appointment(*, appointment_id: int, reason: str) -> Appointment:
    reason = (reason or '').strip()
    if not reason:
        raise BookingError('A cancellation reason is required.', code='reason_required')

    with transaction.atomic():
        appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=appointment_id)
        if appointment.status == Appointment.Status.CANCELLED:
            raise InvalidAppointmentState('This appointment is already cancelled.', code='already_cancelled')
        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = reason
        appointment.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
    return appointment


def reschedule_appointment(*, appointment_id: int, starts_at: datetime) -> Appointment:
    """Move an appointment to a new slot. On any failure the original is left untouched."""
    starts_at = _ensure_aware(starts_at)
    try:
        with transaction.atomic():
            appointment = get_object_or_404(
                Appointment.objects.select_for_update().select_related('patient'), pk=appointment_id
            )
            if appointment.status == Appointment.Status.CANCELLED:
                raise InvalidAppointmentState(
                    'A cancelled appointment cannot be rescheduled.', code='cancelled_appointment'
                )
            if starts_at == appointment.starts_at:
                raise BookingError('The new slot is the same as the current slot.', code='same_slot')

            doctor = Doctor.objects.select_for_update().get(pk=appointment.doctor_id)
            validate_slot(doctor, appointment.patient, starts_at, exclude_appointment_id=appointment.pk)

            appointment.starts_at = starts_at
            appointment.ends_at = starts_at + SLOT_DURATION
            appointment.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
            return appointment
    except IntegrityError:
        raise SlotUnavailable()


def get_available_slots(doctor: Doctor, date) -> list[datetime]:
    """Bookable 30-minute slot start times for `date` (clinic local time)."""
    if not doctor.is_active:
        raise BookingError('This doctor is not currently accepting appointments.', code='doctor_inactive')

    tz = timezone.get_current_timezone()
    day_start = datetime.combine(date, time.min, tzinfo=tz)
    booked = set(
        Appointment.objects.filter(
            doctor=doctor,
            status=Appointment.Status.BOOKED,
            starts_at__gte=day_start,
            starts_at__lt=day_start + timedelta(days=1),
        ).values_list('starts_at', flat=True)
    )
    earliest = timezone.now() + MIN_BOOKING_NOTICE

    slots = set()
    for block in doctor.working_hours.filter(weekday=date.weekday()):
        cursor = datetime.combine(date, block.start_time, tzinfo=tz)
        # Round a block that starts off-grid (e.g. 09:10) up to the next boundary.
        overshoot = timedelta(minutes=cursor.minute % SLOT_MINUTES, seconds=cursor.second)
        if overshoot:
            cursor += SLOT_DURATION - overshoot
        block_end = datetime.combine(date, block.end_time, tzinfo=tz)
        while cursor + SLOT_DURATION <= block_end:
            if cursor >= earliest and cursor not in booked:
                slots.add(cursor)
            cursor += SLOT_DURATION
    return sorted(slots)

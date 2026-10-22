from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class BookingError(APIException):
    """A booking business rule was violated by the request (400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'The booking request is invalid.'
    default_code = 'booking_error'


class SlotUnavailable(BookingError):
    """The requested slot conflicts with an existing active appointment (409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'The requested slot is no longer available.'
    default_code = 'slot_unavailable'


class InvalidAppointmentState(BookingError):
    """The appointment's current status does not allow the operation (409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'The appointment cannot be modified in its current state.'
    default_code = 'invalid_state'


def api_exception_handler(exc, context):
    """DRF's default handler, plus a machine-readable `code` for booking errors."""
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, BookingError):
        response.data['code'] = exc.detail.code
    return response

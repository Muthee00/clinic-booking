from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Appointment, Patient
from .serializers import (
    AppointmentCancelSerializer,
    AppointmentCreateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentSerializer,
    PatientSerializer,
)

ERROR_RESPONSES = {
    400: OpenApiResponse(description='Validation or business-rule error ({"detail", "code"}).'),
    404: OpenApiResponse(description='Not found.'),
    409: OpenApiResponse(description='Slot already taken or appointment in a conflicting state.'),
}


class AppointmentCreateView(APIView):
    @extend_schema(
        request=AppointmentCreateSerializer,
        responses={201: AppointmentSerializer, **ERROR_RESPONSES},
        summary='Book a 30-minute appointment',
        description='Pick a free slot from the availability endpoint and send its date and time.',
        examples=[
            OpenApiExample(
                'Date and time', value={'doctor': 1, 'patient': 1, 'date': '2026-10-23', 'time': '09:00'},
                request_only=True,
            ),
            OpenApiExample(
                'Full starts_at',
                value={'doctor': 1, 'patient': 1, 'starts_at': '2026-10-23T09:00:00+03:00'},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = AppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.book_appointment(**serializer.validated_data)
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)


class AppointmentCancelView(APIView):
    @extend_schema(
        request=AppointmentCancelSerializer,
        responses={200: AppointmentSerializer, **ERROR_RESPONSES},
        summary='Cancel an appointment (reason required)',
    )
    def patch(self, request, pk):
        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.cancel_appointment(
            appointment_id=pk, reason=serializer.validated_data['cancellation_reason']
        )
        return Response(AppointmentSerializer(appointment).data)


class AppointmentRescheduleView(APIView):
    @extend_schema(
        request=AppointmentRescheduleSerializer,
        responses={200: AppointmentSerializer, **ERROR_RESPONSES},
        summary='Move an appointment to a new slot',
        examples=[
            OpenApiExample('Date and time', value={'date': '2026-10-23', 'time': '10:30'}, request_only=True),
        ],
    )
    def patch(self, request, pk):
        serializer = AppointmentRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.reschedule_appointment(
            appointment_id=pk, starts_at=serializer.validated_data['starts_at']
        )
        return Response(AppointmentSerializer(appointment).data)


@extend_schema(summary='Register a patient')
class PatientCreateView(generics.CreateAPIView):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer


@extend_schema(summary="List a patient's upcoming active appointments")
class PatientAppointmentListView(generics.ListAPIView):
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        patient = get_object_or_404(Patient, pk=self.kwargs['pk'])
        return (
            patient.appointments.filter(status=Appointment.Status.BOOKED, starts_at__gte=timezone.now())
            .select_related('doctor', 'patient')
            .order_by('starts_at')
        )

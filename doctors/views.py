from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments import services

from .models import Doctor
from .serializers import AvailabilityQuerySerializer, AvailabilitySerializer, DoctorSerializer


@extend_schema(summary='List doctors with their weekly working hours')
class DoctorListView(generics.ListAPIView):
    queryset = Doctor.objects.prefetch_related('working_hours')
    serializer_class = DoctorSerializer


class DoctorAvailabilityView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter('date', OpenApiTypes.DATE, required=True, description='YYYY-MM-DD')],
        responses={200: AvailabilitySerializer},
        summary='Available 30-minute slots for a doctor on a date',
    )
    def get(self, request, pk):
        doctor = get_object_or_404(Doctor, pk=pk)
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        date = query.validated_data['date']

        slots = services.get_available_slots(doctor, date)
        payload = {
            'doctor': doctor.pk,
            'date': date,
            'timezone': settings.TIME_ZONE,
            'slot_minutes': services.SLOT_MINUTES,
            'slots': [
                {'time': f'{s:%H:%M}', 'starts_at': s, 'ends_at': s + services.SLOT_DURATION} for s in slots
            ],
        }
        return Response(AvailabilitySerializer(payload).data)

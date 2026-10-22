from django.urls import path

from . import views

urlpatterns = [
    path('appointments/', views.AppointmentCreateView.as_view(), name='appointment-create'),
    path('appointments/<int:pk>/cancel/', views.AppointmentCancelView.as_view(), name='appointment-cancel'),
    path(
        'appointments/<int:pk>/reschedule/',
        views.AppointmentRescheduleView.as_view(),
        name='appointment-reschedule',
    ),
    path('patients/', views.PatientCreateView.as_view(), name='patient-create'),
    path(
        'patients/<int:pk>/appointments/',
        views.PatientAppointmentListView.as_view(),
        name='patient-appointments',
    ),
]

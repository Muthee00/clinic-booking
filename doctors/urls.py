from django.urls import path

from . import views

urlpatterns = [
    path('doctors/', views.DoctorListView.as_view(), name='doctor-list'),
    path('doctors/<int:pk>/availability/', views.DoctorAvailabilityView.as_view(), name='doctor-availability'),
]

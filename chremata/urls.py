from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="chremata_dashboard"),
    path("reportes/dia/", views.reporte_diario, name="chremata_reporte_diario"),
]

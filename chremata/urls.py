from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="chremata_dashboard"),
    path("reportes/dia/", views.reporte_diario, name="chremata_reporte_diario"),
    path("reportes/semana/", views.reporte_semana, name="chremata_reporte_semana"),
    path("reportes/mes/", views.reporte_mes, name="chremata_reporte_mes"),
    path("reportes/anio/", views.reporte_anio, name="chremata_reporte_anio"),
]

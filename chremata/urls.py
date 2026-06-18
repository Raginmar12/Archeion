from django.urls import path

from . import views

urlpatterns = [
    path("reportes/dia/", views.reporte_diario, name="chremata_reporte_diario"),
]

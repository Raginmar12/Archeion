"""
URL configuration for archeion project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path

from ledger.views_api import (
    catalogos,
    chremata_operations,
    chremata_schema,
    material_pool,
)

from .views import device_ping

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/device/ping/", device_ping, name="device-ping"),
    path("api/v1/catalogos/", catalogos, name="api-v1-catalogos"),
    path(
        "api/v1/chremata/schema/",
        chremata_schema,
        name="api-v1-chremata-schema",
    ),
    path(
        "api/v1/chremata/material-pool/",
        material_pool,
        name="api-v1-chremata-material-pool",
    ),
    path(
        "api/v1/chremata/operations/",
        chremata_operations,
        name="api-v1-chremata-operations",
    ),
]

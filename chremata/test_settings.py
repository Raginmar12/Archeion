import importlib
import os
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

import archeion.settings as archeion_settings


class ArcheionTimezoneSettingsTests(SimpleTestCase):
    def test_timezone_default_is_matamoros_and_use_tz_stays_enabled(self):
        self.assertEqual(archeion_settings.DEFAULT_TIME_ZONE, "America/Matamoros")
        self.assertEqual(
            settings.TIME_ZONE,
            os.environ.get("ARCHEION_TIME_ZONE", "America/Matamoros"),
        )
        self.assertTrue(settings.USE_TZ)

    def test_timezone_can_be_configured_from_environment(self):
        with patch.dict(os.environ, {"ARCHEION_TIME_ZONE": "America/Mexico_City"}):
            reloaded_settings = importlib.reload(archeion_settings)
            self.assertEqual(reloaded_settings.TIME_ZONE, "America/Mexico_City")

        importlib.reload(archeion_settings)

from django.test import TestCase


class VaultAppTests(TestCase):
    def test_vault_app_is_installed(self):
        self.assertIn("vault", {config.label for config in self.apps.get_app_configs()})

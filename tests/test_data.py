import json
import os
import runpy
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from data import load_data_file


class TestDataLoading(unittest.TestCase):

    def test_wrapped_and_flat_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "weapons.json")
            with patch("data.resource_path", return_value=path):
                for contents in (
                    {"updated": "20230928", "data": {"item": {"decay": "0.1"}}},
                    {"item": {"decay": "0.1"}},
                ):
                    with self.subTest(contents=contents):
                        with open(path, "w", encoding="utf-8") as target:
                            json.dump(contents, target)
                        self.assertEqual(
                            load_data_file("weapons.json"),
                            {"item": {"decay": "0.1"}}
                        )

    def test_legacy_attachment_data_uses_corrected_name(self):
        old_name = "Mayhem MF-Amplfier Alpha (L)"
        new_name = "Mayhem MF-Amplifier Alpha (L)"
        contents = {old_name: {"ammo": 898, "decay": "0.00019", "type": "MF Amp"}}
        with patch("data.load_data_file", return_value=contents):
            attachments = runpy.run_module(
                "data.attachments", run_name="attachment_test"
            )["ALL_ATTACHMENTS"]

        self.assertNotIn(old_name, attachments)
        self.assertEqual(attachments[new_name]["decay"], Decimal("0.00019"))

    def test_pr_items_and_saved_loadout_are_usable(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "import sys, types; "
                    "ocr = types.ModuleType('ocr'); "
                    "ocr.screenshot_window = lambda: None; "
                    "sys.modules['ocr'] = ocr; "
                    "import helpers; "
                    "helpers.get_app_data_path = lambda: '.'; "
                    "from modules.combat import Loadout; "
                    "from data.attachments import ALL_ATTACHMENTS; "
                    "from data.weapons import ALL_WEAPONS; "
                    "loadout = Loadout.load({'amp': 'Mayhem MF-Amplfier Alpha (L)'}); "
                    "assert loadout.amp == 'Mayhem MF-Amplifier Alpha (L)'; "
                    "assert ALL_ATTACHMENTS[loadout.amp]['ammo'] == 898; "
                    "assert all('Mayhem MF-Amplifier ' + variant + ' (L)' in ALL_ATTACHMENTS "
                    "for variant in ('Alpha', 'Beta', 'Gamma', 'Delta')); "
                    "assert all('RDI Energy Amplifier Gamma' + suffix in ALL_ATTACHMENTS "
                    "for suffix in ('', ' (L)')); "
                    "assert all('Omegaton C-120, BGH' + suffix in ALL_WEAPONS "
                    "for suffix in ('', ' (L)'))"
                ],
                cwd=directory,
                env={
                    **os.environ,
                    "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                },
                capture_output=True,
                text=True
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_assets_load_outside_repository_directory(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "from data.weapons import ALL_WEAPONS; "
                    "from data.attachments import ALL_ATTACHMENTS; "
                    "from data.sights_and_scopes import SIGHTS, SCOPES; "
                    "from data.crafting import ALL_RESOURCES, ALL_BLUEPRINTS; "
                    "assert all((ALL_WEAPONS, ALL_ATTACHMENTS, SIGHTS, SCOPES, "
                    "ALL_RESOURCES, ALL_BLUEPRINTS)); "
                    "from decimal import Decimal; "
                    "assert isinstance(next(iter(ALL_WEAPONS.values()))['decay'], Decimal)"
                ],
                cwd=directory,
                env={
                    **os.environ,
                    "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                },
                capture_output=True,
                text=True
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

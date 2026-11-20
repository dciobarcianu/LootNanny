import json
import os
import tempfile
import unittest
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

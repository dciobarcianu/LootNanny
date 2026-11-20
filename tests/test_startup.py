import builtins
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class TestStartupImports(unittest.TestCase):

    def test_import_failure_is_logged_and_propagated(self):
        widgets = types.ModuleType("PyQt5.QtWidgets")
        for name in (
            "QStatusBar", "QFormLayout", "QHeaderView", "QTabWidget",
            "QCheckBox", "QGridLayout", "QComboBox", "QLineEdit", "QLabel",
            "QApplication", "QWidget", "QPushButton", "QVBoxLayout",
            "QTableWidget", "QTableWidgetItem",
        ):
            setattr(widgets, name, object)
        core = types.ModuleType("PyQt5.QtCore")
        core.QFile = object
        core.QTextStream = object
        errors = types.ModuleType("errors")
        errors.log_crash = Mock()
        modules = {
            "PyQt5": types.ModuleType("PyQt5"),
            "PyQt5.QtWidgets": widgets,
            "PyQt5.QtCore": core,
            "pyqtgraph": types.ModuleType("pyqtgraph"),
            "errors": errors,
        }
        original_import = builtins.__import__
        failure = ImportError("startup dependency unavailable")

        def import_with_failure(name, *args, **kwargs):
            if name == "helpers":
                raise failure
            return original_import(name, *args, **kwargs)

        script = Path(__file__).resolve().parents[1] / "LootNanny.py"
        with patch.dict(sys.modules, modules), patch(
            "builtins.__import__", side_effect=import_with_failure
        ):
            with self.assertRaises(ImportError) as raised:
                runpy.run_path(str(script))

        self.assertIs(raised.exception, failure)
        errors.log_crash.assert_called_once_with(failure)


if __name__ == "__main__":
    unittest.main()

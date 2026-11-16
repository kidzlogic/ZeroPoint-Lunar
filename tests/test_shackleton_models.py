import json
import unittest
from pathlib import Path

from shackleton_models import MODEL_DIR, MODEL_SPECS, REPORT_PATH


class ShackletonModelTests(unittest.TestCase):
    def test_five_models_were_trained_on_held_out_shackleton_cells(self):
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(report["models"]), 5)
        self.assertEqual([spec[0] for spec in MODEL_SPECS], [model["id"] for model in report["models"]])
        self.assertGreater(report["held_out_cells"], 50)
        self.assertIn("do not detect water ice", report["note"])
        for model in report["models"]:
            self.assertTrue((MODEL_DIR / model["file"]).is_file())
            self.assertGreater(model["held_out_accuracy"], 0.5)
            self.assertLessEqual(model["held_out_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()

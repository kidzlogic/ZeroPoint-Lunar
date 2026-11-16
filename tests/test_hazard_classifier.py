import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hazard_classifier import load_rules, model_validation_summary


class HazardClassifierTests(unittest.TestCase):
    def test_validation_summary_reports_per_class_support_and_prediction_counts(self):
        metadata = {
            "class_names": ["not_safe", "safe"],
            "validation": {
                "accuracy": 52 / 73,
                "confusion_matrix": [[52, 0], [21, 0]],
                "class_recall": {"not_safe": 1.0, "safe": 0.0},
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "classes.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with patch("hazard_classifier.CLASS_NAMES_PATH", metadata_path):
                summary = model_validation_summary()

        self.assertIn("not_safe: 100% (52/52)", summary)
        self.assertIn("safe: 0% (0/21)", summary)
        self.assertIn("Balanced accuracy 50%", summary)
        self.assertIn("not_safe: 71% (52/73)", summary)
        self.assertIn("safe: unavailable (0 predictions)", summary)
        self.assertIn("Predicted labels -- not_safe: 73, safe: 0", summary)
        self.assertIn("not an independent or mission-representative test set", summary)
        self.assertIn("Image-source provenance is not recorded", summary)

    def test_classifier_rules_make_no_unvalidated_hazard_claims(self):
        rules = load_rules()

        self.assertEqual(set(rules), {"safe", "not_safe"})
        self.assertIn("not a safety finding", rules["safe"]["description"])
        self.assertIn("not a validated hazard determination", rules["not_safe"]["description"])

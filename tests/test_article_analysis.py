import unittest

from article_analysis import analyze_article


class ArticleAnalysisTests(unittest.TestCase):
    def test_reports_distinct_hazard_evidence(self):
        result = analyze_article(
            "The report describes lunar dust near a steep slope and boulders."
        )

        self.assertEqual(
            {finding["category"] for finding in result["findings"]},
            {"Dust / plume", "Rough terrain"},
        )

    def test_ignores_simple_negated_terms(self):
        result = analyze_article("No lunar dust or steep slope was observed.")

        self.assertEqual(result["findings"], [])


if __name__ == "__main__":
    unittest.main()

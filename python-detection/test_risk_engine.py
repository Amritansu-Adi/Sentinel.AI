import unittest

from app.risk_engine import calculate_risk


class RiskEngineTests(unittest.TestCase):
    def test_safe_input_is_allowed(self):
        result = calculate_risk([])
        self.assertEqual((result.score, result.level, result.action, result.categories), (0.0, "SAFE", "ALLOW", ["SAFE"]))

    def test_regex_and_llm_credential_category_is_counted_once(self):
        result = calculate_risk(
            [{"category": "CREDENTIAL_EXPOSURE", "confidence": 0.9}],
            evidence=[{"type": "API_KEY_AWS", "severity": "CRITICAL", "confidence": 0.98, "value_span": [0, 20]}],
        )
        self.assertEqual(result.score, 90.0)
        self.assertEqual((result.level, result.action), ("CRITICAL", "BLOCK"))

    def test_pii_is_blocked_at_the_locked_policy_weight(self):
        result = calculate_risk([], evidence=[{"type": "PAN_CARD", "severity": "HIGH", "confidence": 0.95, "value_span": [0, 10]}])
        self.assertEqual((result.score, result.level, result.action), (80.0, "CRITICAL", "BLOCK"))

    def test_low_relevance_vector_match_does_not_score(self):
        result = calculate_risk([], evidence=[{"doc_id": "doc-1", "classification": "CONFIDENTIAL", "similarity": 0.59}])
        self.assertEqual((result.score, result.level, result.action), (0.0, "SAFE", "ALLOW"))


if __name__ == "__main__":
    unittest.main()

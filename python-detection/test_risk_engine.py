import unittest

from app.risk_engine import NER_CONFIDENCE_FLOOR, calculate_risk


class ScoreLevelTests(unittest.TestCase):
    """SCORE/LEVEL mechanism is unchanged from Task 4.3 — these assert the
    weighted-sum math and threshold mapping still work, decoupled from
    ACTION (see determine_action tests below)."""

    def test_safe_input_is_allowed(self):
        result = calculate_risk([])
        self.assertEqual((result.score, result.level, result.action, result.categories), (0.0, "SAFE", "ALLOW", ["SAFE"]))

    def test_regex_and_llm_credential_category_is_counted_once(self):
        result = calculate_risk(
            [{"category": "CREDENTIAL_EXPOSURE", "confidence": 0.9}],
            evidence=[{"type": "API_KEY_AWS", "severity": "CRITICAL", "confidence": 0.98, "value_span": [0, 20]}],
        )
        self.assertEqual(result.score, 90.0)
        self.assertEqual(result.level, "CRITICAL")

    def test_low_relevance_vector_match_does_not_score(self):
        result = calculate_risk([], evidence=[{"doc_id": "doc-1", "classification": "CONFIDENTIAL", "similarity": 0.59}])
        self.assertEqual((result.score, result.level, result.action), (0.0, "SAFE", "ALLOW"))

    def test_live_policy_config_changes_score(self):
        # Task 7.1: calculate_risk must actually use a passed-in policy_config
        # rather than silently ignoring it.
        policy_config = {"category_weights": {"PII_EXPOSURE": 10}, "thresholds": {"safe_max": 29, "low_max": 59, "high_max": 79}}
        result = calculate_risk(
            [], evidence=[{"type": "EMAIL", "severity": "LOW", "confidence": 0.97, "value_span": [0, 10]}],
            policy_config=policy_config,
        )
        self.assertEqual(result.score, 10.0)
        self.assertEqual(result.level, "SAFE")

    def test_missing_policy_config_falls_back_to_defaults(self):
        result = calculate_risk([], evidence=[{"type": "EMAIL", "severity": "LOW", "confidence": 0.97, "value_span": [0, 10]}])
        self.assertEqual(result.score, 80.0)  # DEFAULT_CATEGORY_WEIGHTS["PII_EXPOSURE"]


class TwoTierActionPolicyTests(unittest.TestCase):
    """Task 7.2 — the three named regression cases from Amritansu's review,
    plus the explicit Tier-1-always-wins case from project.md Task 7.2."""

    def test_single_pan_is_sanitized_not_blocked(self):
        # "this is my pan adfw123e" -> must resolve to SANITIZE, not BLOCK.
        result = calculate_risk([], evidence=[{"type": "PAN_CARD", "severity": "HIGH", "confidence": 0.95, "value_span": [11, 21]}])
        self.assertEqual(result.action, "SANITIZE")
        self.assertTrue(any(f.category == "PII_EXPOSURE" for f in result.flags))

    def test_low_confidence_ner_hit_is_dropped_as_non_evidence(self):
        # "here is the project details" -> must resolve to ALLOW, not BLOCK.
        # A model guess below the confidence floor must not be sanitized or
        # contribute PII severity at all.
        result = calculate_risk([], evidence=[{"type": "ORG", "confidence": 0.8, "value_span": [12, 19]}])
        self.assertEqual((result.score, result.level, result.action, result.categories), (0.0, "SAFE", "ALLOW", ["SAFE"]))
        self.assertEqual(result.flags, [])

    def test_high_confidence_ner_hit_is_sanitized(self):
        result = calculate_risk([], evidence=[{"type": "PERSON", "confidence": NER_CONFIDENCE_FLOOR, "value_span": [0, 5]}])
        self.assertEqual(result.action, "SANITIZE")
        self.assertTrue(any(f.category == "PII_EXPOSURE" for f in result.flags))

    def test_confidential_vector_match_alone_is_blocked(self):
        result = calculate_risk([], evidence=[{"doc_id": "proj-aurora", "classification": "CONFIDENTIAL", "similarity": 0.82}])
        self.assertEqual(result.action, "BLOCK")
        self.assertIsNotNone(result.rewrite_guidance)
        self.assertNotIn("Aurora", result.rewrite_guidance)
        self.assertNotIn("aurora", result.rewrite_guidance.lower())

    def test_confidential_vector_match_plus_api_key_still_blocks(self):
        # Tier 1 wins regardless of what else is present.
        result = calculate_risk(
            [],
            evidence=[
                {"doc_id": "proj-aurora", "classification": "CONFIDENTIAL", "similarity": 0.82},
                {"type": "API_KEY_AWS", "severity": "CRITICAL", "confidence": 0.98, "value_span": [0, 20]},
            ],
        )
        self.assertEqual(result.action, "BLOCK")
        self.assertEqual(result.flags, [])

    def test_confidential_vector_match_wins_over_every_spannable_type(self):
        # Regression coverage for the manual-suite bypasses DBL-03, DBL-09,
        # MULTI-02, and MULTI-07: Tier 1 is evaluated before Tier 2a.
        result = calculate_risk(
            [],
            evidence=[
                {"type": "PAN_CARD", "severity": "HIGH", "confidence": 0.99, "value_span": [0, 10]},
                {"type": "API_KEY_GITHUB", "severity": "CRITICAL", "confidence": 0.99, "value_span": [11, 30]},
                {"type": "PERSON", "confidence": 0.99, "value_span": [31, 36]},
                {"doc_id": "infra-topology", "classification": "CONFIDENTIAL", "similarity": 0.82},
            ],
        )
        self.assertEqual(result.action, "BLOCK")
        self.assertEqual(result.flags, [])

    def test_internal_vector_match_alone_allows_with_advisory_flag(self):
        result = calculate_risk([], evidence=[{"doc_id": "eng-onboarding", "classification": "INTERNAL", "similarity": 0.75}])
        self.assertEqual(result.action, "ALLOW")
        self.assertTrue(len(result.flags) >= 1)

    def test_llm_only_category_with_no_span_allows_with_advisory_flag(self):
        result = calculate_risk([{"category": "SOURCE_CODE_SENSITIVE", "confidence": 0.7, "evidence": "code-like structure"}], evidence=[])
        self.assertEqual(result.action, "ALLOW")
        self.assertTrue(any(f.category == "SOURCE_CODE_SENSITIVE" for f in result.flags))

    def test_no_evidence_allows_with_no_flags(self):
        result = calculate_risk([], evidence=[])
        self.assertEqual(result.action, "ALLOW")
        self.assertEqual(result.flags, [])
        self.assertIsNone(result.rewrite_guidance)

    def test_db_connection_string_is_sanitized_via_span_not_llm_only(self):
        # DB_CONNECTION_STRING maps to SECURITY_SENSITIVE_INFORMATION for
        # scoring, but it IS a spannable regex Finding — must mask via
        # Tier 2a, not fall through to a non-spannable ALLOW+flag.
        result = calculate_risk([], evidence=[{"type": "DB_CONNECTION_STRING", "severity": "CRITICAL", "confidence": 0.95, "value_span": [0, 40]}])
        self.assertEqual(result.action, "SANITIZE")


if __name__ == "__main__":
    unittest.main()

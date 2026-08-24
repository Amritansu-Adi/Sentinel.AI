import unittest

from app.detectors.regex_detector import detect_regex
from app.sanitizer import sanitize


class SanitizerTests(unittest.TestCase):
    def test_replaces_regex_findings_without_retaining_sensitive_values(self):
        text = "Email ada@example.com, PAN ABCDE1234F, key sk_live_abcdefghijklmnop."
        sanitized = sanitize(text, detect_regex(text))
        self.assertEqual(
            sanitized,
            "Email [EMAIL_ADDRESS], PAN [PAN_CARD], key [API_KEY].",
        )
        for raw_value in ("ada@example.com", "ABCDE1234F", "sk_live_abcdefghijklmnop"):
            self.assertNotIn(raw_value, sanitized)

    def test_replaces_ner_spans_and_accepts_json_friendly_lists(self):
        text = "Alice works at SentinelAI."
        sanitized = sanitize(
            text,
            [
                {"type": "PERSON", "value_span": [0, 5], "confidence": 0.99},
                {"type": "ORG", "value_span": [15, 25], "confidence": 0.99},
            ],
        )
        self.assertEqual(sanitized, "[PERSON_NAME] works at [ORGANIZATION].")

    def test_overlapping_findings_are_redacted_once_with_specific_token(self):
        text = "Contact ada@example.com"
        sanitized = sanitize(
            text,
            [
                {"type": "PERSON", "value_span": [8, 11]},
                {"type": "EMAIL", "value_span": [8, 23]},
            ],
        )
        self.assertEqual(sanitized, "Contact [EMAIL_ADDRESS]")
        self.assertNotIn("ada@example.com", sanitized)

    def test_invalid_or_spanless_metadata_never_causes_text_scanning(self):
        text = "Keep ada@example.com unchanged."
        sanitized = sanitize(
            text,
            [
                {"type": "EMAIL", "value_span": [0, 999]},
                {"doc_id": "project-atlas", "classification": "CONFIDENTIAL", "similarity": 0.99},
            ],
        )
        self.assertEqual(sanitized, text)


if __name__ == "__main__":
    unittest.main()

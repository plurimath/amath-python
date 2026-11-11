"""Dialect P (pma) through the installed native wheel: every accepted and
refused amath corpora/pma row against the Ruby reference output
(tests/fixtures/pma-reference.json, generated from amath 71df055)."""
import json
import unittest
from pathlib import Path

import amath

REFERENCE = json.loads((Path(__file__).parent / "fixtures/pma-reference.json").read_text(encoding="utf-8"))
CATEGORIES = 14


class PmaModelTest(unittest.TestCase):
    def test_accepted_rows_match_the_reference_term(self):
        rows = REFERENCE["accepted"]
        self.assertEqual(len(rows), 38)
        for row in rows:
            with self.subTest(row["id"]):
                model = amath.parse_model_json(row["input"], dialect="pma")
                self.assertEqual(model["term"], row["term"])

    def test_refused_rows_match_category_and_offsets(self):
        rows = REFERENCE["refused"]
        self.assertEqual(len(rows), 60)
        seen = set()
        for row in rows:
            with self.subTest(row["id"]):
                with self.assertRaises(amath.ModelParseError) as caught:
                    amath.parse_model_json(row["input"], dialect="pma")
                error = caught.exception
                seen.add(error.refusal_category)
                self.assertEqual(
                    (error.refusal_category, error.byte_offset, error.char_offset),
                    (row["category"], row["byte_offset"], row["char_offset"]),
                )
        self.assertEqual(len(seen), CATEGORIES)

    def test_default_dialect_is_unchanged_and_pma_never_falls_back(self):
        legacy = amath.parse_model_json("x^2")
        self.assertIsInstance(legacy, dict)
        self.assertNotIn("term", legacy)
        with self.assertRaises(amath.ModelParseError):
            amath.parse_model_json("x^2", dialect="pma")
        with self.assertRaises(ValueError):
            amath.parse_model_json("unit(m)", dialect="pma", decimal=",")
        with self.assertRaises(ValueError):
            amath.parse_model_json("unit(m)", dialect="pmx")


if __name__ == "__main__":
    unittest.main()

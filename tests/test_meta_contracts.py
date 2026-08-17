from __future__ import annotations

import unittest

from harness.core.contracts import Evidence, normalize_criteria
from harness.core.verification import verify_criteria


class MetaContractTests(unittest.TestCase):
    def test_mapping_criteria_preserve_ids_and_required_flag(self) -> None:
        criteria = normalize_criteria([
            {"id": "build", "description": "build succeeds"},
            {"id": "lint", "description": "lint is clean", "required": False},
        ])
        self.assertEqual(criteria[0].id, "build")
        self.assertTrue(criteria[0].required)
        self.assertFalse(criteria[1].required)

    def test_optional_missing_criterion_does_not_block(self) -> None:
        criteria = normalize_criteria([
            {"id": "build", "description": "build succeeds"},
            {"id": "lint", "description": "lint is clean", "required": False},
        ])
        result = verify_criteria(
            criteria,
            [Evidence(type="test", criterion_id="build", verified=True)],
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.satisfied_criteria, ("build",))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from harness.core.cache import get_cached_value, set_cached_value


class CacheTests(unittest.TestCase):
    def test_cache_invalidates_when_checked_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            watched = Path(temp_dir) / "watched.txt"
            watched.write_text("one", encoding="utf-8")

            set_cached_value(cache_dir, "key", {"value": "cached"}, check_file=watched)
            self.assertEqual(get_cached_value(cache_dir, "key", check_file=watched), {"value": "cached"})

            time.sleep(0.01)
            watched.write_text("two", encoding="utf-8")

            result = get_cached_value(cache_dir, "key", check_file=watched)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

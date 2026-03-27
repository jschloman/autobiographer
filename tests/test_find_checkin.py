import json
import os
import shutil
import tempfile
import unittest

from find_checkin import find_checkins


class TestFindCheckin(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.checkins_file = os.path.join(self.test_dir, "checkins_test.json")

        self.mock_data = {
            "items": [
                {
                    "createdAt": "2026-01-01T12:00:00Z",
                    "venue": {"name": "Holiday Inn Express Fremont"},
                },
                {"createdAt": "2026-01-02T12:00:00Z", "venue": {"name": "Coffee Shop"}},
            ]
        }

        with open(self.checkins_file, "w", encoding="utf-8") as f:
            json.dump(self.mock_data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_find_checkins(self):
        results = find_checkins(self.test_dir, "Holiday Inn")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], "Holiday Inn Express Fremont")

    def test_find_checkins_no_match(self):
        results = find_checkins(self.test_dir, "Pizza Hut")
        self.assertEqual(len(results), 0)

    def test_find_checkins_invalid_dir(self):
        results = find_checkins("non_existent_dir", "Any")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

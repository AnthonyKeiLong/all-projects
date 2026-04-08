"""Tests for timestamp parsing and normalization."""

import unittest
from datetime import datetime, timezone

from WebFileSync.utils import (
    fmt_dt,
    fmt_size,
    normalize_to_utc,
    parse_http_date,
    sha256_bytes,
)


class TestParseHttpDate(unittest.TestCase):
    """Validate robust parsing of various date formats."""

    def test_rfc2822(self):
        dt = parse_http_date("Wed, 25 Mar 2026 14:22:00 GMT")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 25)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_iso8601_z(self):
        dt = parse_http_date("2026-03-26T09:15:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_iso8601_offset(self):
        dt = parse_http_date("2026-03-26T09:15:00+05:30")
        self.assertIsNotNone(dt)
        # Should be converted to UTC
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.hour, 3)   # 09:15 IST = 03:45 UTC
        self.assertEqual(dt.minute, 45)

    def test_common_tz_abbrs(self):
        dt = parse_http_date("Wed, 25 Mar 2026 14:22:00 EST")
        self.assertIsNotNone(dt)
        # EST = UTC-5 → 14:22 EST = 19:22 UTC
        self.assertEqual(dt.hour, 19)

    def test_empty_string(self):
        self.assertIsNone(parse_http_date(""))

    def test_none(self):
        self.assertIsNone(parse_http_date(None))

    def test_garbage(self):
        self.assertIsNone(parse_http_date("not a date at all"))

    def test_apache_style(self):
        dt = parse_http_date("26/Mar/2026 09:15:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.day, 26)


class TestNormalizeToUtc(unittest.TestCase):

    def test_naive_assumed_utc(self):
        naive = datetime(2026, 3, 26, 12, 0, 0)
        result = normalize_to_utc(naive)
        self.assertEqual(result.tzinfo, timezone.utc)
        self.assertEqual(result.hour, 12)

    def test_aware_converted(self):
        from datetime import timedelta
        tz_plus5 = timezone(timedelta(hours=5))
        aware = datetime(2026, 3, 26, 15, 0, 0, tzinfo=tz_plus5)
        result = normalize_to_utc(aware)
        self.assertEqual(result.tzinfo, timezone.utc)
        self.assertEqual(result.hour, 10)


class TestSha256(unittest.TestCase):

    def test_known_hash(self):
        data = b"hello world"
        h = sha256_bytes(data)
        self.assertEqual(
            h, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )


class TestFormatters(unittest.TestCase):

    def test_fmt_size_bytes(self):
        self.assertEqual(fmt_size(500), "500.0 B")

    def test_fmt_size_kb(self):
        self.assertIn("KB", fmt_size(2048))

    def test_fmt_size_none(self):
        self.assertEqual(fmt_size(None), "?")

    def test_fmt_dt_none(self):
        self.assertEqual(fmt_dt(None), "—")

    def test_fmt_dt_value(self):
        dt = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)
        self.assertIn("2026-03-26", fmt_dt(dt))


if __name__ == "__main__":
    unittest.main()

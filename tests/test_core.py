import unittest
from datetime import datetime, timezone, timedelta

from coordinated_mars_time import CoordinatedMarsTime, LocalMarsSolarTime, utc_to_cmt
from coordinated_mars_time.core import (
    local_mean_solar_time,
    _wrap_into_day,
    _to_unix_seconds,
    _MARS_SOL_SECONDS,
)


class TestUtcToCmt(unittest.TestCase):
    """Behavioural tests for ``utc_to_cmt``.

    The absolute readout depends on the phase convention chosen in ``core``;
    these tests pin the behaviour of THIS implementation, not the physical
    correctness of the ephemeris.
    """

    def test_returns_coordinated_mars_time_instance(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = utc_to_cmt(dt)
        self.assertIsInstance(result, CoordinatedMarsTime)

    def test_hours_in_valid_range(self):
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_to_cmt(dt)
        self.assertGreaterEqual(result.hours, 0)
        self.assertLessEqual(result.hours, 23)

    def test_minutes_in_valid_range(self):
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_to_cmt(dt)
        self.assertGreaterEqual(result.minutes, 0)
        self.assertLess(result.minutes, 60)

    def test_seconds_in_valid_range(self):
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_to_cmt(dt)
        self.assertGreaterEqual(result.seconds, 0)
        self.assertLess(result.seconds, 60)

    def test_deterministic_for_same_input(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        a = utc_to_cmt(dt)
        b = utc_to_cmt(dt)
        self.assertEqual(a, b)

    def test_naive_datetime_treated_as_utc(self):
        """A naive datetime must produce the same result as an explicitly
        UTC-aware datetime with the same wall-clock reading."""
        naive = datetime(2024, 1, 1, 0, 0, 0)
        aware = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(utc_to_cmt(naive), utc_to_cmt(aware))

    def test_non_utc_timezone_converted_to_utc(self):
        """A datetime in a non-UTC zone must be reduced to UTC before
        conversion; the wall-clock reading alone is not enough."""
        utc_noon = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # UTC+2 at 14:00 local is the same instant as 12:00 UTC.
        plus_two = timezone(timedelta(hours=2))
        local_two = datetime(2024, 1, 1, 14, 0, 0, tzinfo=plus_two)
        self.assertEqual(utc_to_cmt(utc_noon), utc_to_cmt(local_two))

    def test_sol_number_advances_over_one_sol(self):
        """Adding one Mars sol worth of Earth seconds to the input must
        advance the sol number by exactly one, without changing the
        within-sol clock readout."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        later = base + timedelta(seconds=_MARS_SOL_SECONDS)
        a = utc_to_cmt(base)
        b = utc_to_cmt(later)
        self.assertEqual(b.sol_number, a.sol_number + 1)
        self.assertEqual((b.hours, b.minutes, b.seconds),
                         (a.hours, a.minutes, a.seconds))

    def test_pre_reference_epoch_is_supported(self):
        """Dates before the reference epoch must not raise; the sol number
        simply becomes non-positive."""
        early = datetime(1950, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = utc_to_cmt(early)
        self.assertLess(result.sol_number, 0)
        self.assertGreaterEqual(result.hours, 0)

    def test_clock_wraps_within_a_sol(self):
        """Two instants separated by slightly under a full Mars sol must
        have the same within-sol clock readout up to the rounding of the
        second."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        just_under = base + timedelta(seconds=_MARS_SOL_SECONDS - 1.0)
        a = utc_to_cmt(base)
        b = utc_to_cmt(just_under)
        # The within-sol readout should be within 1 second of the original.
        a_s = a.hours * 3600 + a.minutes * 60 + a.seconds
        b_s = b.hours * 3600 + b.minutes * 60 + b.seconds
        diff = abs(a_s - b_s)
        self.assertLessEqual(diff, 1)


class TestLocalMarsSolarTime(unittest.TestCase):
    """Tests for longitude-dependent local solar time."""

    def test_prime_meridian_matches_cmt(self):
        """At longitude 0, LMST equals MTC (by construction)."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        cmt = utc_to_cmt(dt)
        lmst = local_mean_solar_time(dt, 0.0)
        self.assertEqual((lmst.hours, lmst.minutes, lmst.seconds),
                         (cmt.hours, cmt.minutes, cmt.seconds))

    def test_180_east_is_12_hours_behind(self):
        """At 180°E, local noon on the prime meridian is local midnight,
        i.e. the local clock is 12 hours behind MTC."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        cmt = utc_to_cmt(dt)
        lmst = local_mean_solar_time(dt, 180.0)
        expected_hours = (cmt.hours - 12) % 24
        self.assertEqual(lmst.hours, expected_hours)

    def test_longitude_wraps_360_east_equivalent_to_zero(self):
        """360°E is the same meridian as 0°E; the local time must match."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        at_zero = local_mean_solar_time(dt, 0.0)
        at_360 = local_mean_solar_time(dt, 360.0)
        self.assertEqual((at_360.hours, at_360.minutes, at_360.seconds),
                         (at_zero.hours, at_zero.minutes, at_zero.seconds))

    def test_negative_longitude_advances_clock(self):
        """West longitudes (negative east) should see local noon *before*
        the prime meridian — i.e. a larger within-sol readout for the same
        instant — because the Sun transits there earlier in absolute time."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        prime = local_mean_solar_time(dt, 0.0)
        west = local_mean_solar_time(dt, -15.0)
        # 15° west => +1 hour relative to the prime meridian.
        self.assertEqual(west.hours, (prime.hours + 1) % 24)

    def test_return_type(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = local_mean_solar_time(dt, 45.0)
        self.assertIsInstance(result, LocalMarsSolarTime)
        self.assertEqual(result.longitude_east, 45.0)

    def test_lmst_string_format(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = local_mean_solar_time(dt, 0.0)
        s = result.as_lmst_string()
        self.assertEqual(len(s), 8)
        self.assertEqual(s[2], ":")
        self.assertEqual(s[5], ":")


class TestInternals(unittest.TestCase):
    """Direct tests for the small helper functions.

    These are part of the implementation contract, not private trivia:
    ``_wrap_into_day`` defines the clock-face behaviour and
    ``_to_unix_seconds`` defines the UTC handling.
    """

    def test_wrap_into_day_positive(self):
        self.assertAlmostEqual(_wrap_into_day(90000.0), 3600.0, places=10)

    def test_wrap_into_day_negative(self):
        self.assertAlmostEqual(_wrap_into_day(-100.0), 86300.0, places=10)

    def test_wrap_into_day_zero(self):
        self.assertEqual(_wrap_into_day(0.0), 0.0)

    def test_to_unix_seconds_naive_treated_as_utc(self):
        naive = datetime(1970, 1, 1, 0, 0, 0)
        self.assertEqual(_to_unix_seconds(naive), 0.0)

    def test_to_unix_seconds_aware_uses_utc_equivalent(self):
        plus_two = timezone(timedelta(hours=2))
        local = datetime(1970, 1, 1, 2, 0, 0, tzinfo=plus_two)
        self.assertEqual(_to_unix_seconds(local), 0.0)

    def test_to_unix_seconds_known_value(self):
        # 2024-01-01T00:00:00Z = 1704067200 Unix seconds.
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_to_unix_seconds(dt), 1704067200.0)


if __name__ == "__main__":
    unittest.main()

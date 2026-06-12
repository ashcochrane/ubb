"""Pure-math tests for graduated/package cumulative pricing + tier validation.

No DB: RateCard instances are constructed unsaved — compute_cumulative /
compute_marginal / validate_tiers are pure functions of the card's fields.
"""
import random

import pytest

from apps.metering.pricing.models import RateCard, validate_tiers
from apps.metering.pricing.services.pricing_service import _event_bands


def _graduated_card(tiers):
    return RateCard(card_type="price", metric_name="m",
                    pricing_model="graduated", tiers=tiers)


def _package_card(rate, block, fixed=0):
    return RateCard(card_type="price", metric_name="m", pricing_model="package",
                    rate_per_unit_micros=rate, unit_quantity=block,
                    fixed_micros=fixed, tiers=[])


def _random_graduated_tiers(rng):
    n = rng.randint(1, 6)
    tiers, lower = [], 0
    for i in range(n):
        is_last = i == n - 1
        up_to = None if is_last else lower + rng.randint(1, 5_000)
        tiers.append({
            "up_to": up_to,
            "rate_per_unit_micros": rng.randint(0, 10_000),
            "unit_quantity": rng.choice([1, 7, 1_000, 1_000_000]),
            "flat_micros": rng.choice([0, 0, rng.randint(1, 5_000_000)]),
        })
        if up_to is not None:
            lower = up_to
    return tiers


def _random_split(rng, total):
    """Split `total` into an ordered list of event sizes, including zeros and
    band-straddling jumps (cut points are uniform over [0, total])."""
    k = rng.randint(1, 8)
    cuts = sorted(rng.randint(0, total) for _ in range(k - 1)) if total > 0 else []
    points = [0] + cuts + [total]
    parts = [b - a for a, b in zip(points, points[1:])]
    for _ in range(rng.randint(0, 3)):  # sprinkle explicit zero-unit events
        parts.insert(rng.randrange(len(parts) + 1), 0)
    return parts


class TestTelescopingProperty:
    def test_graduated_marginals_telescope_exactly(self):
        rng = random.Random(20260612)
        for _ in range(200):
            tiers = _random_graduated_tiers(rng)
            validate_tiers("price", "graduated", tiers)  # generated configs are valid
            card = _graduated_card(tiers)
            total = rng.randint(0, 20_000)
            prior, marginal_sum = 0, 0
            for part in _random_split(rng, total):
                marginal = card.compute_marginal(prior, part)
                assert marginal >= 0
                marginal_sum += marginal
                after = prior + part
                # Per-step band invariant: sum of band micros == the marginal
                band_sum = sum(b["micros"] for b in _event_bands(card, prior, after))
                assert band_sum == marginal, (
                    f"band_sum {band_sum} != marginal {marginal} "
                    f"for prior={prior} part={part}")
                prior = after
            assert prior == total
            assert marginal_sum == card.compute_cumulative(total)

    def test_graduated_cumulative_monotone_nonnegative(self):
        rng = random.Random(424242)
        for _ in range(200):
            card = _graduated_card(_random_graduated_tiers(rng))
            q1 = rng.randint(0, 20_000)
            q2 = q1 + rng.randint(0, 20_000)
            t1, t2 = card.compute_cumulative(q1), card.compute_cumulative(q2)
            assert 0 <= t1 <= t2

    def test_package_marginals_telescope_exactly(self):
        rng = random.Random(777)
        for _ in range(200):
            block = rng.randint(1, 1_000)
            card = _package_card(rng.randint(0, 1_000_000), block,
                                 fixed=rng.choice([0, 123, 1_000_000]))
            total = rng.randint(0, 10 * block)
            prior, marginal_sum = 0, 0
            for part in _random_split(rng, total):
                marginal = card.compute_marginal(prior, part)
                assert marginal >= 0
                marginal_sum += marginal
                prior += part
            assert marginal_sum == card.compute_cumulative(total)

    def test_package_in_block_event_is_zero_marginal(self):
        card = _package_card(5_000_000, 1_000, fixed=100)
        assert card.compute_marginal(0, 1) == 5_000_100   # block 1 + period fee
        assert card.compute_marginal(1, 998) == 0          # inside block 1
        assert card.compute_marginal(999, 1) == 0          # exactly fills block 1
        assert card.compute_marginal(1_000, 1) == 5_000_000  # opens block 2


class TestKnownValues:
    def test_graduated_two_band_ladder(self):
        card = _graduated_card([
            {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
            {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
        ])
        assert card.compute_cumulative(0) == 0
        assert card.compute_cumulative(50) == 500
        assert card.compute_cumulative(100) == 1_000
        assert card.compute_cumulative(150) == 1_250
        # band-straddling marginal: 40 @10 + 20 @5
        assert card.compute_marginal(60, 60) == 500

    def test_graduated_flat_micros_charged_on_band_entry(self):
        card = _graduated_card([
            {"up_to": 10, "rate_per_unit_micros": 0, "unit_quantity": 1, "flat_micros": 100},
            {"up_to": None, "rate_per_unit_micros": 0, "unit_quantity": 1, "flat_micros": 900},
        ])
        assert card.compute_cumulative(0) == 0
        assert card.compute_cumulative(1) == 100      # entered band 1
        assert card.compute_cumulative(10) == 100     # still only band 1
        assert card.compute_cumulative(11) == 1_000   # entered band 2
        # the crossing event's marginal carries band 2's flat
        assert card.compute_marginal(10, 1) == 900

    def test_graduated_half_up_rounding_matches_compute_division(self):
        card = _graduated_card([
            {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 2},
        ])
        assert card.compute_cumulative(1) == 3  # (1*5 + 1) // 2 — half-up

    def test_graduated_default_unit_quantity_is_one_million(self):
        card = _graduated_card([{"up_to": None, "rate_per_unit_micros": 5}])
        assert card.compute_cumulative(1_000_000) == 5

    def test_compute_raises_for_tiered_models(self):
        graduated = _graduated_card(
            [{"up_to": None, "rate_per_unit_micros": 1, "unit_quantity": 1}])
        with pytest.raises(ValueError, match="period context"):
            graduated.compute(10)
        with pytest.raises(ValueError, match="period context"):
            _package_card(10, 5).compute(10)

    def test_compute_cumulative_raises_for_untiered_models(self):
        card = RateCard(card_type="price", metric_name="m", pricing_model="per_unit",
                        rate_per_unit_micros=1, unit_quantity=1)
        with pytest.raises(ValueError, match="tiered"):
            card.compute_cumulative(5)

    def test_compute_cumulative_rejects_negative(self):
        card = _package_card(10, 5)
        with pytest.raises(ValueError, match="negative"):
            card.compute_cumulative(-1)

    def test_none_units_treated_as_zero(self):
        card = _package_card(10, 5, fixed=3)
        assert card.compute_cumulative(None) == 0
        assert card.compute_marginal(None, None) == 0


GOOD_TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10},
    {"up_to": None, "rate_per_unit_micros": 5},
]


class TestValidateTiers:
    # --- accepted shapes ---

    def test_graduated_good_tiers_ok(self):
        validate_tiers("price", "graduated", GOOD_TIERS)

    def test_graduated_all_optional_keys_ok(self):
        validate_tiers("price", "graduated", [
            {"up_to": 5, "rate_per_unit_micros": 0, "unit_quantity": 7, "flat_micros": 0},
            {"up_to": None, "rate_per_unit_micros": 1, "unit_quantity": 1, "flat_micros": 9},
        ])

    @pytest.mark.parametrize("model", ["per_unit", "flat"])
    @pytest.mark.parametrize("card_type", ["cost", "price"])
    def test_untiered_with_empty_tiers_ok(self, card_type, model):
        validate_tiers(card_type, model, [])
        validate_tiers(card_type, model, None)  # JSON null treated as empty

    def test_package_empty_tiers_ok_on_price(self):
        validate_tiers("price", "package", [])

    def test_exactly_twenty_tiers_ok(self):
        tiers = [{"up_to": i + 1, "rate_per_unit_micros": 1} for i in range(19)]
        tiers.append({"up_to": None, "rate_per_unit_micros": 1})
        validate_tiers("price", "graduated", tiers)

    # --- rejections ---

    @pytest.mark.parametrize("model", ["graduated", "package"])
    def test_tiered_models_forbidden_on_cost_cards(self, model):
        with pytest.raises(ValueError, match="cost cards"):
            validate_tiers("cost", model, GOOD_TIERS if model == "graduated" else [])

    @pytest.mark.parametrize("model", ["per_unit", "flat", "package"])
    def test_non_graduated_models_require_empty_tiers(self, model):
        with pytest.raises(ValueError, match="must be empty"):
            validate_tiers("price", model, GOOD_TIERS)

    def test_tiers_must_be_a_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            validate_tiers("price", "graduated", {"up_to": None})

    def test_graduated_empty_tiers_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            validate_tiers("price", "graduated", [])

    def test_more_than_twenty_tiers_rejected(self):
        tiers = [{"up_to": i + 1, "rate_per_unit_micros": 1} for i in range(20)]
        tiers.append({"up_to": None, "rate_per_unit_micros": 1})
        with pytest.raises(ValueError, match="at most 20"):
            validate_tiers("price", "graduated", tiers)

    def test_tier_must_be_an_object(self):
        with pytest.raises(ValueError, match="must be an object"):
            validate_tiers("price", "graduated", ["nope"])

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValueError, match="unknown keys"):
            validate_tiers("price", "graduated",
                           [{"up_to": None, "rate_per_unit_micros": 1, "rate": 2}])

    def test_missing_up_to_rejected(self):
        with pytest.raises(ValueError, match="missing up_to"):
            validate_tiers("price", "graduated", [{"rate_per_unit_micros": 1}])

    def test_missing_rate_rejected(self):
        with pytest.raises(ValueError, match="missing rate_per_unit_micros"):
            validate_tiers("price", "graduated", [{"up_to": None}])

    def test_last_tier_must_be_unbounded(self):
        with pytest.raises(ValueError, match="up_to=None"):
            validate_tiers("price", "graduated",
                           [{"up_to": 5, "rate_per_unit_micros": 1}])

    def test_only_last_tier_may_be_unbounded(self):
        with pytest.raises(ValueError, match="only the last"):
            validate_tiers("price", "graduated", [
                {"up_to": None, "rate_per_unit_micros": 1},
                {"up_to": None, "rate_per_unit_micros": 1},
            ])

    def test_up_to_must_be_strictly_increasing(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            validate_tiers("price", "graduated", [
                {"up_to": 100, "rate_per_unit_micros": 1},
                {"up_to": 100, "rate_per_unit_micros": 1},
                {"up_to": None, "rate_per_unit_micros": 1},
            ])

    @pytest.mark.parametrize("bad", [0, -5, "10", 1.5, True])
    def test_up_to_must_be_positive_int(self, bad):
        with pytest.raises(ValueError, match="up_to"):
            validate_tiers("price", "graduated", [
                {"up_to": bad, "rate_per_unit_micros": 1},
                {"up_to": None, "rate_per_unit_micros": 1},
            ])

    @pytest.mark.parametrize("bad", [-1, "5", 1.5, None, True])
    def test_rate_must_be_nonnegative_int(self, bad):
        with pytest.raises(ValueError, match="rate_per_unit_micros"):
            validate_tiers("price", "graduated",
                           [{"up_to": None, "rate_per_unit_micros": bad}])

    @pytest.mark.parametrize("bad", [0, -1, "5", 1.5, True])
    def test_unit_quantity_must_be_positive_int(self, bad):
        with pytest.raises(ValueError, match="unit_quantity"):
            validate_tiers("price", "graduated", [
                {"up_to": None, "rate_per_unit_micros": 1, "unit_quantity": bad}])

    @pytest.mark.parametrize("bad", [-1, "5", 1.5, True])
    def test_flat_micros_must_be_nonnegative_int(self, bad):
        with pytest.raises(ValueError, match="flat_micros"):
            validate_tiers("price", "graduated", [
                {"up_to": None, "rate_per_unit_micros": 1, "flat_micros": bad}])

"""`core.controls` — which spend control a stop came from, derived from why it
fired (slice 6 §1, #458).

Pure — no model, no query. The two maps are held to the generated vocabulary
by CONSTANT IDENTITY, never by spelling, and the two questions this module
refuses to answer (a cascade's family, an unknown reason's) are asserted as
refusals rather than left to a `.get()` that would answer `None` and let a
caller publish a blank on a closed field.
"""
import pytest

from core import controls
from core.vocabulary import (
    CEILING_BASIS_COST,
    CEILING_BASIS_TIME,
    CONTROL_FAMILY_ADMISSION_CONTROL,
    CONTROL_FAMILY_CEILING,
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    CONTROL_FAMILY_VALUES,
    CONTROL_FAMILY_WALLET_POLICY,
    REASON_CODE_ABSOLUTE_DEADLINE,
    REASON_CODE_CUSTOMER_SPEND_POOL,
    REASON_CODE_HARD_FLOOR,
    REASON_CODE_KNOWN_VALUES,
    REASON_CODE_PARENT_EXPIRED,
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_SILENCE_WINDOW,
    REASON_CODE_TASK_COGS_CEILING,
)


class TestTheFamilyAStopCameFrom:
    def test_the_units_own_ceiling_and_both_time_bounds_are_the_ceilings(self):
        for reason in (REASON_CODE_TASK_COGS_CEILING, REASON_CODE_SILENCE_WINDOW,
                       REASON_CODE_ABSOLUTE_DEADLINE):
            assert controls.control_family(reason) is CONTROL_FAMILY_CEILING, reason

    def test_the_pools_stop_is_the_pools_and_the_floors_is_the_wallet_policys(self):
        assert (controls.control_family(REASON_CODE_CUSTOMER_SPEND_POOL)
                is CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        assert (controls.control_family(REASON_CODE_HARD_FLOOR)
                is CONTROL_FAMILY_WALLET_POLICY)

    def test_a_cascades_reason_names_no_family_of_its_own(self):
        """Contained work stopped by its parent's end inherits the PARENT's
        family (§1), which this module cannot know — so it refuses rather
        than answering with a family the child never crossed."""
        for reason in (REASON_CODE_PARENT_KILLED, REASON_CODE_PARENT_EXPIRED):
            assert reason in controls.INHERITED_FROM_THE_PARENT
            with pytest.raises(controls.NoFamilyOfItsOwn):
                controls.control_family(reason)

    def test_a_reason_this_module_has_never_heard_of_is_refused(self):
        with pytest.raises(controls.NoFamilyOfItsOwn):
            controls.control_family("something_else")
        with pytest.raises(controls.NoFamilyOfItsOwn):
            controls.control_family("")

    def test_every_known_reason_is_either_mapped_or_inherited(self):
        """The map is complete over the registry's known stop reasons, so a
        coinage that arrives without a family here is a red test and not a
        blank on the wire."""
        assert (set(controls.FAMILY_BY_REASON) | controls.INHERITED_FROM_THE_PARENT
                == set(REASON_CODE_KNOWN_VALUES))
        assert not set(controls.FAMILY_BY_REASON) & controls.INHERITED_FROM_THE_PARENT

    def test_admission_control_stops_nothing_and_so_no_reason_maps_to_it(self):
        assert CONTROL_FAMILY_ADMISSION_CONTROL not in set(
            controls.FAMILY_BY_REASON.values())
        assert set(controls.FAMILY_BY_REASON.values()) <= CONTROL_FAMILY_VALUES


class TestWhichBasisACeilingFiredOn:
    def test_the_cogs_ceiling_is_cost_and_either_window_is_time(self):
        assert controls.ceiling_basis(REASON_CODE_TASK_COGS_CEILING) is CEILING_BASIS_COST
        assert controls.ceiling_basis(REASON_CODE_SILENCE_WINDOW) is CEILING_BASIS_TIME
        assert controls.ceiling_basis(REASON_CODE_ABSOLUTE_DEADLINE) is CEILING_BASIS_TIME

    def test_a_stop_that_was_not_a_ceilings_has_no_basis(self):
        for reason in (REASON_CODE_CUSTOMER_SPEND_POOL, REASON_CODE_HARD_FLOOR,
                       REASON_CODE_PARENT_KILLED, REASON_CODE_PARENT_EXPIRED,
                       "something_else", ""):
            assert controls.ceiling_basis(reason) is None, reason

    def test_exactly_the_ceilings_reasons_carry_a_basis(self):
        """The two maps agree on which reasons are a ceiling's: a reason with
        a basis is in the ceiling family, and every ceiling reason has one."""
        with_a_basis = set(controls.CEILING_BASIS_BY_REASON)
        ceilings = {reason for reason, family in controls.FAMILY_BY_REASON.items()
                    if family is CONTROL_FAMILY_CEILING}
        assert with_a_basis == ceilings

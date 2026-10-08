# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   python verify_integration.py EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:6894a8e53712aeab483db913594682d3d46b4ae1102aec4b37f7003b9ff85e3d"

import json
import sys
from decimal import Decimal, InvalidOperation

# Every quantity read off a response, by Event Type, and where.
DECLARED_PATHS = {
}

# Every supplier cost read off a response, by Event Type: where, what it
# represents, and its currency or where that is read. A cost of zero is
# a cost: what is checked is that each value is there, is what a cost
# may be, and converts.
DECLARED_COSTS = {
    "billed.search": {
        # provider_response_cost_micros.source_path = ["billing","amount_minor"] · event_type "billed.search"
        "source_path": ["billing", "amount_minor"],
        # provider_response_cost_micros.amount_representation = "minor_units" · event_type "billed.search"
        "amount_representation": "minor_units",
        "currency": "",
        # currency.source_path = ["billing","currency"] · event_type "billed.search"
        "currency_path": ["billing", "currency"],
    },
}

_MISSING = object()


def _resolve(document, segments):
    found = document
    for segment in segments:
        if not isinstance(found, dict) or segment not in found:
            return _MISSING
        found = found[segment]
    return found


# A cost a supplier reports is converted to whole micros once, here,
# through Decimal. A binary float is refused. An amount finer than a
# micro is refused, never rounded.
class ReportedCostNotRepresentable(ValueError):
    pass


class ReportedCostCurrencyRefused(ValueError):
    pass


_MICROS_PER_MAJOR_UNIT = 1000000
_MICROS_PER_MINOR_UNIT = {
    "aud": 10000,
    "brl": 10000,
    "cad": 10000,
    "chf": 10000,
    "czk": 10000,
    "dkk": 10000,
    "eur": 10000,
    "gbp": 10000,
    "hkd": 10000,
    "inr": 10000,
    "mxn": 10000,
    "nok": 10000,
    "nzd": 10000,
    "pln": 10000,
    "sek": 10000,
    "sgd": 10000,
    "usd": 10000,
    "zar": 10000,
}
_MICROS_LIMIT = 2 ** 63 - 1
_EXPONENT_LIMIT = 40


def _minor_unit(currency):
    try:
        return _MICROS_PER_MINOR_UNIT[currency.lower()]
    except (AttributeError, KeyError):
        raise ReportedCostCurrencyRefused(
            f"{currency!r} is not a currency UBB holds"
        ) from None


def _pin_currency(declared, reported):
    pinned = (declared or "").strip().lower()
    supplied = (reported or "").strip().lower()
    if not pinned and not supplied:
        raise ReportedCostCurrencyRefused(
            "this cost is denominated in no currency"
        )
    if pinned and supplied and pinned != supplied:
        raise ReportedCostCurrencyRefused(
            f"the supplier reported this cost in another currency than the declared one: {supplied!r}, not {pinned!r}"
        )
    code = pinned or supplied
    _minor_unit(code)
    return code


def _to_micros(amount, representation, currency):
    if representation == "micros":
        multiplier = 1
    elif representation == "minor_units":
        multiplier = _minor_unit(currency)
    elif representation == "major_units_decimal":
        multiplier = _MICROS_PER_MAJOR_UNIT
    else:
        raise ReportedCostNotRepresentable(
            f"{representation!r} is not an amount representation"
        )
    if isinstance(amount, bool):
        raise ReportedCostNotRepresentable(
            f"{amount!r} is a flag, not a reported cost"
        )
    if isinstance(amount, float):
        raise ReportedCostNotRepresentable(
            f"{amount!r} is a binary float, and a reported cost is money: pass its decimal text or an integer"
        )
    if amount is None:
        raise ReportedCostNotRepresentable(
            "no cost was reported, and a missing cost is not a zero"
        )
    try:
        exact = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise ReportedCostNotRepresentable(
            f"{amount!r} is not a number"
        ) from None
    if not exact.is_finite():
        raise ReportedCostNotRepresentable(
            f"{amount!r} is not a finite amount"
        )
    sign, digits, exponent = exact.as_tuple()
    digits = list(digits)
    while exponent < 0 and len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    unsigned = 0
    for digit in digits:
        unsigned = unsigned * 10 + digit
    if abs(exponent) > _EXPONENT_LIMIT:
        raise ReportedCostNotRepresentable(
            f"{amount!r} is not an amount of money that can be held: its exponent is out of range"
        )
    if exponent >= 0:
        micros = unsigned * 10 ** exponent * multiplier
    else:
        micros, remainder = divmod(unsigned * multiplier, 10 ** -exponent)
        if remainder:
            raise ReportedCostNotRepresentable(
                f"{amount!r} is not a whole number of micros, and a reported cost is never rounded"
            )
    if micros > _MICROS_LIMIT:
        raise ReportedCostNotRepresentable(
            f"{amount!r} is more micros than can be held"
        )
    return -micros if sign else micros


# A cost read off your supplier's response is read as it is there: an
# integer, a decimal string, or a Decimal where you parse JSON with
# parse_float=Decimal. A binary float is refused: read the response's
# integer or decimal string instead.
# A currency read off the response that UBB does not hold is refused
# here. One it holds that is not your UBB currency is refused by UBB
# when the event is recorded, and that refusal reaches you as the SDK's
# error.
def _read_amount(amount):
    if isinstance(amount, float):
        raise ReportedCostNotRepresentable(
            f"{amount!r} is a binary float, and a reported cost is money: read the response's integer or its decimal string instead"
        )
    return amount


def _read_currency(currency):
    if not isinstance(currency, str):
        raise ReportedCostCurrencyRefused(
            f"{currency!r} is not a currency code: a currency read off a response is text"
        )
    return currency


COST = "provider_response_cost_micros"
CURRENCY = "currency"


def _check_cost(cost, document, check):
    amount = _resolve(document, cost["source_path"])
    check(amount is not _MISSING, COST, "resolves in the captured response")
    admissible = isinstance(amount, (int, str)) and not isinstance(amount, bool)
    if amount is not _MISSING:
        check(admissible, COST, "is an integer or a decimal string, as a reported cost must be")
    supplied = None
    if cost["currency_path"] is not None:
        supplied = _resolve(document, cost["currency_path"])
        check(supplied is not _MISSING, CURRENCY, "resolves in the captured response")
        if supplied is _MISSING:
            return
    try:
        currency = _pin_currency(
            cost["currency"], None if supplied is None else _read_currency(supplied))
    except ReportedCostCurrencyRefused:
        currency = None
    if cost["currency_path"] is not None:
        check(currency is not None, CURRENCY, "is a currency UBB holds")
    if admissible and currency is not None:
        try:
            _to_micros(_read_amount(amount), cost["amount_representation"], currency)
            converts = True
        except (ReportedCostNotRepresentable, ReportedCostCurrencyRefused):
            converts = False
        check(converts, COST, "converts to whole micros exactly")


def main(arguments) -> int:
    known = [*DECLARED_PATHS, *(event_type for event_type in DECLARED_COSTS
                                if event_type not in DECLARED_PATHS)]
    if not known:
        print("No selected Event Type reads a quantity or a cost off a response. There is nothing to check.")
        return 0
    if len(arguments) != 3 or arguments[1] not in known:
        print("usage: python verify_integration.py EVENT_TYPE captured-response.json")
        print("Event Types with a quantity or a cost read off a response:")
        for event_type in known:
            print(f"  {json.dumps(event_type, ensure_ascii=False)}")
        return 2
    declared = DECLARED_PATHS.get(arguments[1], {})
    with open(arguments[2], encoding="utf-8") as captured:
        document = json.load(captured)
    failures = 0

    def check(passed, quantity, message):
        nonlocal failures
        failures += 0 if passed else 1
        verdict = "ok  " if passed else "FAIL"
        print(f"  {verdict} {json.dumps(quantity, ensure_ascii=False)} {message}")

    for quantity, segments in declared.items():
        value = _resolve(document, segments)
        check(value is not _MISSING, quantity, "resolves in the captured response")
        if value is _MISSING:
            continue
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        check(number, quantity, "is a number")
        if number:
            check(value != 0, quantity, "is not zero (a constant zero is what a path to the wrong field reads)")
        shared = [other for other, path in declared.items()
                  if other != quantity and path == segments]
        check(not shared, quantity, "is read from a path no other quantity is read from")
    if arguments[1] in DECLARED_COSTS:
        _check_cost(DECLARED_COSTS[arguments[1]], document, check)

    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("Every check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

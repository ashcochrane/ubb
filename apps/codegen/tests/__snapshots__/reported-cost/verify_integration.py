# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   python verify_integration.py EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:36af256701e35c0c04a595d3a40f537c399286364e9f614a285bac8e4db9deef"

import json
import sys

# Every quantity read off a response, by Event Type, and where.
DECLARED_PATHS = {
}

_MISSING = object()


def _resolve(document, segments):
    found = document
    for segment in segments:
        if not isinstance(found, dict) or segment not in found:
            return _MISSING
        found = found[segment]
    return found


def main(arguments) -> int:
    if not DECLARED_PATHS:
        print("No selected Event Type reads a quantity off a response. There is nothing to check.")
        return 0
    if len(arguments) != 3 or arguments[1] not in DECLARED_PATHS:
        print("usage: python verify_integration.py EVENT_TYPE captured-response.json")
        print("Event Types with a quantity read off a response:")
        for event_type in DECLARED_PATHS:
            print(f"  {json.dumps(event_type, ensure_ascii=False)}")
        return 2
    declared = DECLARED_PATHS[arguments[1]]
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

    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("Every check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

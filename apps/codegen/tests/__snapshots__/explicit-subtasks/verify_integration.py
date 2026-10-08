# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   python verify_integration.py EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:a996fccd584d4e02052a806d2048502898ff186ec700c66b33e73f9e1185bd85"

import json
import sys

# Every quantity read off a response, by Event Type, and where.
DECLARED_PATHS = {
    "gemini.generate": {
        # measurements.candidate_tokens.source_path = ["usage_metadata","candidates_token_count"] · event_type "gemini.generate"
        "candidate_tokens": ["usage_metadata", "candidates_token_count"],
        # measurements.prompt_tokens.source_path = ["usageMetadata","promptTokenCount"] · event_type "gemini.generate"
        "prompt_tokens": ["usageMetadata", "promptTokenCount"],
    },
}

# Every supplier cost read off a response, by Event Type: where, what it
# represents, and its currency or where that is read. A cost of zero is
# a cost: what is checked is that each value is there, is what a cost
# may be, and converts.
DECLARED_COSTS = {
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

    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("Every check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

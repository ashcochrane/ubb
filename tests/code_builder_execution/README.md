# The Code Builder's execution suite (Seam C)

Generated integration code proved by running it, unmodified, against the real
application (#582; ADR-0008 §5; #158 §5.3–§5.5). For every scenario, on every
target it names:

1. a tenant of its own is seeded, and its configuration declared through its
   own routes (`_tenant.py`; only the tenant row and its first key are written
   directly, because no route creates them);
2. the Integration Blueprint is resolved through its route, and must be the
   readiness the scenario declares before anything else happens;
3. `ubb-codegen` renders it (`apps/codegen/scripts/render.ts`);
4. the files are written to disk unpatched, and a sha256 of each is taken as
   it is written (`_harness.py`);
5. the run is given `UBB_BASE_URL` and `UBB_API_KEY` and nothing of this
   suite's own (no database, secret or setting reaches it);
6. a customer's own script runs it — the glue a customer writes, which pastes
   the rendered call-site blocks into its own code as rendered and supplies
   only runtime values (`_customer.py`) — Python on this machine against the
   SDK in this tree, shell in a pinned image; the checksums are held before
   and after every run;
7. the scenario asserts what the run did and what the application recorded.

The application is the platform itself, served by pytest-django's
`live_server` over the real Postgres and Redis. There is no real supplier:
responses come from `provider_responses/`, and the generated code still walks
the declared path through them.

## Adding a scenario

A capability ticket adds its scenario to `SCENARIOS` in `_scenarios.py` and
changes nothing in the harness: a `configure` that declares its configuration
through the routes, the `works` its customer's code runs (data, not code), an
`expect` over the runs and the records, the `readiness` its Blueprint must
have, and where a shell artifact runs. #583 added a supplier cost read off the
response (`response-cost`), a currency read beside it that the server
refuses (`response-currency-refused`) and a cost written as a float that
neither target sends (`response-cost-written-as-a-float`), against the three
billed responses in `provider_responses/`, which a scenario names with
`Response("<name>")`;
#584 adds a constant Measurement, #586 a fixed-price kind. #585 added no
scenario: it extended two declarations, #569's names in
`_customer.STOP_METADATA` and their values in `_scenarios._the_stop`, which
both stop scenarios assert through. It also pins, in
`test_the_shell_matrix.py`, that a stop's figures reach `UBB_STOP_REQUESTED`
as the digits UBB wrote on every jq of the standing matrix: there a local
stand-in answers the record, because the real application never writes
figures at the extremes of a signed 64-bit amount.

## What runs where

- **Python** runs on this machine with `sys.executable`; the SDK it imports is
  `ubb-sdk/` in this tree.
- **Shell** runs in an image built from `images/<name>/Dockerfile`, every
  layer pinned by digest and nothing installed by a package manager:
  `shell` (Debian: dash and bash 5.2, jq 1.7.1, curl 8.11.1), `bash-3.2` and
  `oldest-jq` (jq 1.5), which with `shell` make the standing matrix of shells;
  and the four preflight fixtures `without-jq`, `without-curl`, `jq-1.4` and
  `curl-7.75`. On Linux a container shares this machine's network; on Docker
  Desktop it reaches the server as `host.docker.internal`, which the server
  is told to accept.

## Running

From the git root, with Postgres, Redis, Node 22.6 or later (it runs the
renderer's TypeScript directly) and Docker:

```
python -m pytest tests/code_builder_execution
```

There is no skip: a machine without Node or Docker fails the suite. It uses
the platform's test database, so never run it beside another platform
`pytest` against the same one — point `DATABASE_URL` at another database name
(Django makes `test_<name>`), and `UBB_TEST_REDIS_DB` at another Redis index.

CI runs it in its own job, `code-builder-execution`, on every push and pull
request; `tests/contracts/test_the_execution_suite_is_enforced.py` holds that
job to being unconditional and able to fail the run, and every image to being
pinned.

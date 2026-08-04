# Code Builder output — worked example (#157 prototype)

**This is not a specification, and it is not real generated code.** It is a
hand-built worked example of what the Code Builder would emit, produced so that
[#157](https://github.com/ashcochrane/ubb/issues/157) has something concrete to
react to. The reading notes are next door:
[`../2026-08-04-code-builder-output-notes.md`](../2026-08-04-code-builder-output-notes.md).

It renders a **paper model.** None of the endpoints, request fields or response
fields used here exist on `main` today, and several are named provisionally —
§6 of the notes lists exactly which and why that matters.

## The tenant it was generated for

Northwind Research is fictional, and everything below is presented as *their*
declarations, not as anything UBB ships. Map #137 constraint 5 forbids a
UBB-shipped catalogue of providers, event types or prices, and #156 §8.2 forbids
the builder inventing tenant vocabulary for an empty registry. A prototype
choosing a plausible tenant to render is a different act from a product
inventing one for a real user — but it is close enough that it is worth saying
out loud.

| Declared | |
|---|---|
| Task kind | `report_generation` · `event_priced` · COGS ceiling 5.000000 USD · silence 900 s · duration 21600 s |
| Required Grouping Fields | `environment`, `workspace_id` (task scope) · `stage` (event scope) |
| Subtask kind | `source_research` · COGS ceiling 2.000000 USD |
| Event Type | `anthropic-messages` · `calculated` · shape `anthropic.messages.python.v1` · `input_tokens`, `output_tokens` |
| Event Type | `openai-embeddings` · `calculated` · shape `openai.embeddings.rest.v1` · `prompt_tokens` |
| Event Type | `serp-search` · `reported` · cost supplied by the caller · `searches` (constant 1) |

## What is here

```
CALL-SITES.md                     the per-call-site blocks, one copy button each
python/
  ubb_integration.py              the artifact · verdict COMPLETE
  ubb_integration.incomplete.py   the same builder, earlier configuration · verdict INCOMPLETE
  verify_integration.py           generated verification
  .env.example                    generated, and deliberately empty
http/
  ubb_integration.sh              the artifact · verdict INCOMPLETE, and the notes explain why
  verify_integration.sh           generated verification
  .env.example
```

Read `python/ubb_integration.py` first: it is the reference shape. Then
`http/ubb_integration.sh`, which is incomplete on purpose — one Event Type
declares its mapping against a Python SDK response shape, which a curl target
cannot read, and watching the builder refuse rather than guess is the point.
Then `python/ubb_integration.incomplete.py` for the missing-configuration and
suspect-mapping states.

## Checked

`python -m py_compile` passes on all three Python files; `bash -n` passes on both
shell files. Nothing here has been executed — there is no server to execute it
against, and the API it calls does not exist yet.

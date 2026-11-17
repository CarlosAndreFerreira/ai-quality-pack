# JSON output of the evidence commands

`memory.py gate --json`, `repro --json`, `counterexample --json` and `evidence --json` print one JSON object on stdout in place of the text for a person. The exit code is the same as without `--json`. A message of a usage error stays on stderr, and stdout is still one JSON object.

`schema` is 1. A new key does not change this number. A key that goes away, or that changes its meaning, does. A test of the pack fails when a key is not in this file.

## `gate`, `repro`, `counterexample`

| Key | Type | Meaning |
|---|---|---|
| `schema` | number | The version of this format |
| `command` | text | `gate`, `repro` or `counterexample` |
| `exit` | number | The exit code of the command |
| `result` | text | The result from the record that the command wrote in the run log. See the values below |
| `why` | text or null | The reason that the command gave for the result. For a gate that failed: the command that failed |
| `record` | object or null | The fields of the record: `result`, `kind`, `failed`, `commands`, `seconds`, `warnings`, `test`, `base`, `recorded_test`, `timed_out`, `policy`, `id`. Only the fields that the command wrote are there. `null` when the command wrote no record |
| `output` | text | The text that the command prints without `--json` (the last 6000 characters). For a person; do not read a result from it |

Values of `result`:

- `gate`: `pass`, `fail`, `skipped` (no change since the last pass).
- `repro`: `verified`, `not-reproduced`, `still-failing`, `wrong-failure`, `base-timeout`.
- `counterexample`: `shown` (with `record.kind`: `regression`, `not-fixed`, `base-not-seen`, `base-unknown`), `not-shown`, `wrong-failure`, `timeout`.
- Each command: `no-record` when the command stopped before it wrote a record (a usage error, exit code 2), and `ok` for `--check` with exit code 0.

Only `repro` with `verified` shows a fix, and only `counterexample` with `shown` and `record.kind` `regression` shows that the change broke something.

## `evidence`

| Key | Type | Meaning |
|---|---|---|
| `schema` | number | The version of this format |
| `command` | text | `evidence` |
| `exit` | number | 0, or 1 with `--strict` when something is not verified or a warning exists |
| `ref` | text | The commit that the change is compared with |
| `risk` | text | `LOW`, `MEDIUM` or `HIGH` |
| `verdict` | text | `SUPPORTED`, `FAIL` or `UNKNOWN`, as `memory.py verdict` gives it |
| `records` | object | `gate`, `reproduction`, `reproduction_test`, `counterexample`, `mutation`, `tests_confirmed` (`by a person`, `no`, or `none` when no reproduction with a recorded test is there) |
| `not_verified` | list of text | Each item of the "Not verified" part of the block |
| `warnings` | list of text | The warnings of the block |
| `markdown` | text | The block for a pull request |

## Example

```bash
python3 .agents/skills/long-horizon/scripts/memory.py gate --json > gate.json || echo "the gate did not pass"
python3 -c "import json; d = json.load(open('gate.json')); print(d['result'], d['why'])"
```

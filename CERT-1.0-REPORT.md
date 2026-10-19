# httprange 1.0.0 certification report

The 1.0.0 certification bar (19 items) applied to httprange. PyPI has 0.2.0 only
(checked on 2026-10-19 at https://pypi.org/pypi/httprange/json), so 1.0.0 must upgrade
cleanly from it and every behaviour change against it is listed in the CHANGELOG.

Progress:
- [x] Branch `release/1.0.0` created from `main` (3e1d009, the 0.2.0 code)
- [x] Baseline gates on 0.2.0
- [x] API review and 1.0.0 changes (item 1)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [x] Ground truth: RFC texts fetched live, reference implementations run (item 7)
- [x] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.2.0, every Python (items 8, 10, 13, 14)
- [ ] Five QA lenses report PASS (item 19): rounds 1 to 3 findings fixed, re-verification pending
- [ ] Independent reviewer reports PASS (item 16)
- [x] Gates (item 15), run at ae86f77
- [ ] PR #3 open from `release/1.0.0`, trace guard CLEAN (item 17); merge and publish left to the maintainer

## Scorecard (author)

| # | Item | Result |
| --- | --- | --- |
| 1 | Public API reviewed for stability | PASS: 30 names; parameter names, fields and defaults of 0.2.0 kept and pinned; every behaviour change in the CHANGELOG |
| 2 | `__all__` exact, no private imports in docs | PASS: `test_the_package_exports_nothing_else`; public classes report `httprange` as their module |
| 3 | Docstrings with runnable examples, doctests | PASS: every public name and member has an example; `pytest --doctest-modules src` 43 passed |
| 4 | Typed end to end | PASS: `mypy --strict src tests`, `py.typed` shipped, no `Any` in the public API |
| 5 | Typed, documented, bounded errors | PASS: `RangeError` (a `ValueError`) and seven subclasses, wrong types included; messages quote at most 40 characters of input |
| 6 | Contract tests of every public name | PASS: `test_contract.py`, `test_contract_api.py`, `test_types.py` |
| 7 | Real ground truth | PASS: see below |
| 8 | Real e2e from the wheel | PASS: wheel in a fresh venv driven from an empty folder, console script and `python -m`, upgrade in place from PyPI 0.2.0 |
| 9 | Seeded fuzz, no crash, hang or blowup | PASS: see below |
| 10 | Supported Pythons | PASS: CPython 3.10.22, 3.11.17, 3.12.15, 3.13.16, 3.14.8, 3.14.8 free-threaded |
| 11 | README and `twine check` | PASS: `twine check --strict`, absolute links, verified comparison |
| 12 | Dated CHANGELOG section | PASS: 1.0.0, 2026-10-19 |
| 13 | pyproject 1.0.0, Production/Stable | PASS |
| 14 | sdist and wheel contents | PASS |
| 15 | Gates each exit 0 | PASS: see Gates |
| 18 | Contracts bite (mutations) | PASS: 19 author mutants, all killed (one after a new contract) |

## Baseline on 0.2.0 (before any change)

`ruff format --check .`, `ruff check .` and `mypy --strict src tests` exit 0 on 3e1d009.
`pytest --doctest-modules src` collected no doctest: no public name had a runnable example.

## API review (item 1)

Kept: the 30 public names of 0.2.0 with their parameter names, fields and defaults,
pinned by `tests/test_contract_api.py`. Widened: the `data` and `body` annotations of the
multipart functions (`bytes | bytearray | memoryview`, all already accepted). Changed, all
in the CHANGELOG and each asserted on both releases by `tests/test_upgrade_changes.py`
and `tests/test_upgrade_changes_wire.py` (31 cases): wrong argument types raise
`RangeError`; value objects validate their fields; `ContentRange` lower-cases its unit;
range counting before spec syntax; stricter multipart building and parsing; the RFC 850
fifty-year rule on the full instant; bounded messages; `python -m httprange`; the stray
`annotations` name is gone. `tests/test_upgrade.py` runs 57,000 seeded calls on
0.2.0 and 1.0.0 and finds no other difference.

## Ground truth (item 7)

Fetched by `scripts/fetch_upstream.py` into the ignored `tests/upstream` folder;
`tests/upstream/MANIFEST.json` records URL, revision, size, sha256 and licence, and the
tests check the hash before reading. All six were fetched again on 2026-10-19 on another
machine and matched the manifest. Nothing fetched is committed or shipped.

- RFC 9110, RFC 9112, RFC 5234 and verified erratum 7306 (`test_spec_grammar.py`): the
  ABNF of RFC 9110 Appendix A with the RFC 5234 core rules becomes regular expressions and
  random sentences (`tests/abnf.py`); seeded sentences and their mutations must get the
  same verdict from the grammar and from the strict parsers for `Range`,
  `Content-Range`, `Accept-Ranges` and HTTP-dates.
- RFC 9110 sections 14, 15.3.7 and 15.5.17 (`test_spec_ranges.py`): every example header
  and expected offset is cut from the text.
- RFC 9110 5.6.7, 8.8.3.2 and 13.1.5 (`test_spec_conditional.py`): the three example
  dates, the strong comparison column of Table 3, the If-Range steps.
- RFC 9110 14.6 and RFC 2046 5.1.1 (`test_spec_multipart.py`): the example messages cut
  from the text, the `bchars` set and the body grammar.
- Reference implementations run live (Node.js 24.18.0): range-parser 1.3.0 (the npm
  tarball behind Express and send) agrees inside RFC 9110 and each departure is asserted;
  werkzeug 3.1.9 and aiohttp 3.14.5 likewise; Python's `email`, `email.utils`,
  `http.cookiejar` and `time.asctime` as oracles for bodies and dates; curl 8 against a
  server built on the library; PyPI 0.2.0 as described above.

## Fuzz and hostile input (item 9)

`tests/test_fuzz.py`: three seeds of 1,500 to 5,000 cases per property (range requests
round trip or fail typed; resolution keeps its invariants, including request order after
coalescing; Content-Range, multipart bodies and dates round trip; mutated bodies fail
typed; If-Range is symmetric and decisions consistent). `tests/test_hostile.py`: 16 input
shapes timed at 25,000 and 200,000 characters (linear growth), and 18 entry points fed
100,000 characters with messages that quote at most 40 of them.
`tests/test_robustness.py`: the smallest interpreter digit limit, subclasses that lie
about themselves, a released `memoryview`, caller exceptions passed through, 8 threads.

## Author mutation round (item 18)

Each mutant applied alone to a fresh clone of the pushed branch on another machine, the
full suite (fetched sources, Node.js reference, werkzeug, aiohttp, 0.2.0 oracle) run with
`-x` and a 300 s per-test limit. M19 survived the first round; the contract
`test_rejects_a_given_boundary_found_in_a_part` now covers a boundary at the start,
middle and end of a part, and the second round at ae86f77 killed all 19.

| Id | Module | Mutation | Caught by |
| --- | --- | --- | --- |
| M1 | `_spec.py` | suffix range one byte short | `test_cli.py::test_resolve_prints_content_ranges` |
| M2 | `_spec.py` | first position equal to the length accepted | `test_contract.py::test_each_public_name_keeps_its_promise[UnsatisfiableRange]` |
| M3 | `_spec.py` | last position clamped one past the end | `test_e2e_server.py::test_single_ranges_give_206_and_exact_bytes` |
| M4 | `_resolve.py` | `-0` on an empty body treated as satisfiable | `test_resolve.py::test_empty_representation_with_a_suffix_selects_nothing` |
| M5 | `_resolve.py` | overlap limit off by one | `test_cli.py::test_resolve_prints_content_ranges` |
| M6 | `_resolve.py` | adjacent ranges not coalesced | `test_contract.py::test_each_public_name_keeps_its_promise[resolve_ranges]` |
| M7 | `_resolve.py` | coalesced ranges in offset order, not request order | `test_e2e_server.py::test_three_ranges_arrive_in_request_order` |
| M8 | `_resolve.py` | range count limit off by one | `test_cli.py::test_resolve_enforces_max_ranges` |
| M9 | `_content_range.py` | `ContentRange.length` off by one | `test_contract_api.py` (and `test_content_range_parse.py`) |
| M10 | `_content_range.py` | unit case kept | `test_content_range_parse.py::test_parses_rfc_examples` |
| M11 | `_content_range.py` | first and last swapped when parsing | `test_cli.py::test_errors_go_to_stderr_with_exit_1` |
| M12 | `_conditional.py` | weak entity tags match | `test_conditional.py::test_entity_tags_use_strong_comparison` |
| M13 | `_conditional.py` | `date_is_strong=False` ignored | `test_conditional.py::test_weak_dates_and_malformed_dates_never_match` |
| M14 | `_dates.py` | leap second 60 rejected | `test_conditional.py::test_leap_second_is_read_as_fifty_nine` |
| M15 | `_dates.py` | fifty-year rule by calendar year only | `test_conditional.py::test_fifty_year_rule_compares_full_dates` |
| M16 | `_decision.py` | a single range answered as multipart | `test_decision.py::test_single_range_is_a_single_part_206` |
| M17 | `_decision.py` | method compared without case | `test_decision.py::test_range_is_ignored_for_methods_other_than_get[get]` |
| M18 | `_multipart.py` | `max_parts` off by one | `test_multipart.py::test_caps_the_number_of_parts` |
| M19 | `_multipart.py` | boundary at the start of a part not detected | `test_multipart.py::test_rejects_a_given_boundary_found_in_a_part[--abcxx]` |

## Packaging, e2e and Pythons (items 8, 10, 13, 14)

- `tests/test_e2e_wheel.py` (`HTTPRANGE_E2E=1`, `HTTPRANGE_E2E_PYPI=1`): builds wheel and
  sdist, inspects both, installs the wheel in a fresh venv and runs a consumer program
  with `-I` from an empty folder, the `httprange` script and `python -m httprange`; then
  installs 0.2.0 from PyPI, upgrades it in place and checks the same results.
  `tests/test_e2e_cli.py` drives the installed console script by subprocess.
- Wheel: the package modules, `py.typed`, `__main__.py`, the licence and metadata only.
  Sdist: sources, tests, docs, scripts and `tests/upstream/MANIFEST.json`; no fetched
  files, no reports, no caches. `twine check --strict` passes for both.
- Every supported interpreter (installed on the other machine, as on this PC), the
  wheel in a fresh venv and the sdist's own suite run with `src` removed, at ae86f77:
  CPython 3.10.22, 3.11.17, 3.12.15, 3.13.16, 3.14.8 and 3.14.8 free-threaded, 965 passed
  and no skip each (the two e2e modules run separately). 3.8 and 3.9 are below
  `requires-python`.

## Gates (item 15)

At ae86f77 on another machine from a fresh clone, CPython 3.14.2, each command on its
own, with the fetched sources, Node.js, werkzeug, aiohttp, curl, the 0.2.0 oracle,
`HTTPRANGE_E2E=1` and `HTTPRANGE_E2E_PYPI=1`: `ruff format --check .`, `ruff check .`,
`mypy --strict src`, `mypy --strict src tests` and `pytest` (976 passed, no skip) all
exit 0.

## QA lenses (item 19) and independent review (item 16)

### Round 1 (at 5c39f0e): 5 lenses, 25 findings, all fixed

Verdicts: a (API and docs) 5 findings, b (correctness) 2, c (adversarial) 4,
d (packaging and e2e) 3, e (contract strength) 11. None was disputed.

| Lens / id | Finding | Fix | Contract |
| --- | --- | --- | --- |
| a F1 | Docstring, README and GUIDE examples were not run by the gate; the e2e handler was a copy | Public functions report `httprange` as their module (`doctest.testmod(httprange)`: 75 examples); README and GUIDE blocks run with their claims checked; the e2e server runs the GUIDE handler from the file | `test_docs.py`, `range_server.py` |
| a F2 | `BytePart`, `MultipartBody`, `RangeDecision`, `RangeRequest` annotations rejected documented inputs | Explicit `__init__` taking `bytes`/`bytearray`/`memoryview` and lists; fields unchanged | `test_contract_inputs.py` (part of `mypy --strict tests`) |
| a F3 | GUIDE: the 4000-digit cap counts significant digits only | GUIDE, CHANGELOG and the error message say so | `test_the_digit_cap_counts_significant_digits_only` |
| a F4 | Two CHANGELOG 1.0.0 statements did not match 0.2.0 | Reworded after running both releases (416 came from a comma count; only non-token methods are quoted) | wire tests unchanged |
| a F5 | README: `content_range` is also `None` for a 200 | Comment fixed and checked by the README runner | `test_readme_quick_start_comment_holds_for_every_status` |
| b F1 | A leap second `:60` matched `:59` in If-Range | Date parse keeps a leap flag; dates match only with equal flags | `test_a_leap_second_*` |
| b F2 | `resolve()` doc called its empty-body raise the RFC 416 case | 0.1 behaviour kept and documented, pointing to `resolve_ranges` | `test_legacy_resolve_refuses_every_spec_on_an_empty_representation` |
| c F1 | `to_utc` used the subclass's `astimezone`/`utcoffset`; invalid offsets leaked `ValueError`/`TypeError` | Fields read through the `datetime` descriptors, offset by the base method, errors mapped to `RangeError` | `test_contract_objects.py` |
| c F2 | Subclass `byte_range`/`as_slice` overrides steered results | Caller subclasses of `RangeSpec`, `ByteRange`, `ContentRange`, `BytePart`, `RangePolicy` copied to plain instances | `test_contract_objects.py` |
| c F3 | `repr` failed under `sys.set_int_max_str_digits(640)` | Own `__repr__` with `int_text`; error args hold the message only | `test_*_print_under_the_smallest_digit_limit` |
| c F4 | `repr(UnsupportedRangeUnit)` echoed the whole unit | `args == (message,)` | `test_error_args_hold_the_message_only` |
| d F1 | `--help`/`--version` exited 120 with a closed reader | Argparse exits flush through the same guard: exit 1, nothing on stderr | `test_cli_contract.py` (closed pipe, subprocess) |
| d F2 | `release.ps1` refused any existing project name | Refuses only an already published version (guard run against live PyPI: 1.0.0 passes, 0.2.0 refused) | script |
| d F3 | Opt-in tests were undocumented and silently skipped | CONTRIBUTING lists them; `check.ps1 -Full` fetches, sets them and fails on any skip (`HTTPRANGE_FULL=1`) | `conftest.py` hook |
| e F1 to F10 | M10, M11, M56, M73, M75, M84, M86, M85, M66, M67 survived the default gate | New always-run contracts | `test_contract_edges.py`, `test_cli_contract.py` |
| e F11 | M39, M51, M64, M68, M72, M74 were caught only by opt-in tests | Self-contained copies, written by hand from the grammar | `test_contract_edges.py` |

Every behaviour change is listed in the CHANGELOG 1.0.0 section.

Commits: 38fa10d (the fixes), da874da and 3051b81 (two contracts made exact after the
mutation check below).

Mutation check of this round, one mutant at a time against the round's test files
(a kill there is a kill by the whole suite), on the other machine at da874da:

| Mutant | Caught by |
| --- | --- |
| M10 inner zeros of `int_text` dropped | `test_wide_numbers_print_and_parse_exactly` |
| M11 leading zeros counted toward the cap | `test_the_digit_cap_counts_significant_digits_only` |
| M56 `last >= length` relaxed to `>` | `test_a_decision_range_must_end_before_the_length` |
| M73 quoted-pair backslash kept | `test_a_quoted_boundary_unescapes_its_quoted_pairs` |
| M75 DEL allowed in a field value | `test_control_characters_and_del_are_refused_in_a_part_content_type` |
| M84 `range:` line for a single range | `test_decide_prints_exact_lines_for_a_single_range` |
| M86 `--last-modified` ignored | `test_decide_matches_a_date_if_range_against_last_modified` |
| M85 `cut()` removed from usage errors | `test_error_messages_are_cut_to_200_characters` |
| M85 `cut()` removed from library errors | `test_a_long_library_error_is_cut_too` (added in 3051b81; it survived at da874da) |
| M66 boundary collision retry removed | `test_a_random_boundary_that_collides_with_the_data_is_drawn_again` |
| M67 up-front range check removed | `test_a_range_past_the_data_raises_the_base_error` |
| M39 tab accepted after the unit | `test_content_range_needs_one_space_after_the_unit` |
| M51 obs-text dropped from entity tags | `test_obs_text_entity_tags_match_by_strong_comparison` |
| M64 unit agreement check removed | `test_parts_must_agree_on_the_range_unit` |
| M68 duplicate part Content-Type allowed | `test_a_part_with_two_content_types_is_refused` |
| M72 boundary trailing space allowed | `test_bad_boundary_parameters_are_refused` (survived at 38fa10d, which matched the wrong error; exact since da874da) |
| M74 duplicate boundary parameter allowed | `test_bad_boundary_parameters_are_refused` |
| Leap flag dropped | `test_a_leap_second_matches_only_itself` |
| `to_utc` reads the subclass again | `test_a_datetime_subclass_cannot_change_the_formatted_date` |
| Spec subclasses kept as given | `test_spec_subclasses_resolve_as_their_fields_say` |
| `RangeSpec.__repr__` removed | `test_values_print_under_the_smallest_digit_limit` |
| Unit back in `args` | `test_error_args_hold_the_message_only` |
| Argparse exit not flushed | `test_a_closed_reader_gives_exit_1_and_nothing_on_stderr` |
| Broken `parse_range` docstring example | `test_every_public_example_runs_from_the_package` |

Gates at 3051b81 on the other machine (CPython 3.14.2, fresh venv from the pushed
branch): `ruff format --check .`, `ruff check .`, `mypy --strict src`,
`mypy --strict src tests` and `pytest` exit 0 (on a clean clone at 38fa10d: 734 passed,
320 skipped; with the upstream files fetched at 3051b81: 1016 passed, 39 skipped).
`scripts/check.ps1 -Full` exits 0 at 3051b81: 1055 passed, no skip.

### Round 2 (at cdf7fa7): lenses a, c and e, 13 findings, all fixed

Lens a re-verified its F1 to F5 as fixed and reported F6. Lens c re-verified its F1 to
F4 as fixed and reported N1. Lens e re-verified its F1 to F11 as fixed (every earlier
mutant now killed by the default gate) and reported ten surviving mutants, G1 to G10.
None was disputed.

| Lens / id | Finding | Fix | Contract |
| --- | --- | --- | --- |
| a F6 | Wrong-type errors said "a tuple" and "bytes" for arguments that also take a list, `bytearray` or `memoryview` | Messages say "a tuple or list" and "bytes, bytearray or memoryview"; CHANGELOG lists the checks | `test_a_wrong_type_error_names_every_accepted_type` |
| c N1 | `RangeRequest` kept `RangeSpec` subclasses, so `str()` used their `__str__` (CR/LF or a crash) | `RangeRequest` stores plain `RangeSpec` copies, like every other value class; CHANGELOG updated | `test_a_range_request_stores_plain_specs_and_prints_their_fields` |
| e G1 | `ContentRange` repr of a huge `complete_length` under a digit limit untested | Test added | `test_every_field_of_a_span_and_a_policy_prints_under_the_digit_limit` |
| e G2 | `RangePolicy` repr of huge fields under a digit limit untested | Test added | same test |
| e G3 | `BytePart` copy of a `ContentRange` subclass untested | Test added | `test_a_part_stores_a_plain_content_range` |
| e G4 | Part copy in `encode_multipart_byteranges` untested | Test added: a part whose `data` changes after construction is refused | `test_encode_rechecks_each_part_as_it_reads_now` |
| e G5 | Policy copy in `resolve_ranges` untested | Test added: a policy whose `coalesce_gap` turns negative is refused | `test_resolve_rechecks_a_policy_as_it_reads_now` |
| e G6 | `fold` of an ambiguous local time not pinned | Test added for `when`, `last_modified` and `now` | `test_the_fold_picks_the_reading_of_an_ambiguous_local_time` |
| e G7 | Microseconds not pinned through the UTC move | Test added | `test_microseconds_count_when_moving_to_utc` |
| e G8 | `OverflowError` path of the UTC move untested | Test added at both ends of the year range for `when`, `now`, `last_modified` | `test_a_moment_outside_the_utc_years_raises_range_error` |
| e G9 | A print that fails (not only the flush) untested | Test added with a standard output that fails on write | `test_a_failing_print_gives_exit_1` |
| e G10 | The `OSError` branch around argument parsing untested (reachable on 3.10) | Test added with a standard output that fails on write | `test_help_into_a_failing_stdout_gives_exit_1` |

Mutation check of this round, one mutant at a time against `test_contract_copies.py`,
`test_cli_contract.py` and `test_contract_objects.py`, on this PC (CPython 3.13; G10 on
CPython 3.10.19, where the branch is reachable): G1 to G10 and N1 (specs kept as given)
are all killed. The F6 and N1 contracts failed on cdf7fa7 before the fix.

Lens a also noted, as not a finding, that `test_every_private_module_example_runs`
attempts no examples now that the package-level doctest run covers them; it is kept as a
guard against an example being added to a private module only.

Commit: dba3cf5 (fixes and contracts). Gates at dba3cf5 on the other machine (CPython
3.14.2, fresh clone and venv): `scripts/check.ps1 -Full` exits 0 (`ruff format --check .`,
`ruff check .`, `mypy --strict src`, `mypy --strict tests`, then `pytest` with the
fetched sources, the 0.2.0 oracle, Node.js, werkzeug, aiohttp, curl and both e2e
switches: 1072 passed, no skip).

### Round 3 (at e95782c): lens e, 6 findings, all fixed

Lens e re-verified its G1 to G10 as fixed (N05, N11, N17, N19, N21, N28, N29, N34 and N37
killed by the default gate; N36 killed on CPython 3.10.19 and unreachable on 3.14, where
argparse swallows the error) and reported six surviving probes on the round 2 code. All
six were gaps in the tests, not wrong behaviour, so no library code and no CHANGELOG
entry changed. None was disputed.

| Lens / id | Finding | Fix | Contract |
| --- | --- | --- | --- |
| e E1 (P09) | No `RangeRequest` spec that has `start` and `end` but is not a `RangeSpec` | Test added with a named tuple of those fields | `test_range_request_refuses_a_spec_lookalike` |
| e E2 (P10) | The lower-cased unit was only tested through `parse_range_request` | Test constructs `RangeRequest` with `Bytes` and `ITEMS` | `test_range_request_stores_the_unit_lower_cased` |
| e E3 (P16) | The tuple branch of the plain item copy was not tested with a tuple subclass that overrides `__iter__` | Tuple subclass added next to the list one | `test_subclasses_cannot_steer_a_result` |
| e E4 (P17) | The 40-character cut of type names in wrong-type errors was untested | Test passes an object whose type name is 5000 characters and asserts the exact message | `test_a_wrong_type_error_cuts_a_huge_type_name` |
| e E5 (P18) | No `bytearray` subclass with its own `__bytes__` | Subclass added; `data` stays `b"ab"` | `test_subclasses_cannot_steer_a_result` |
| e E6 (P20) | A plain `bytearray` subclass as part data was untested | Subclass added in the same test | same test |

Mutation check of this round, one mutant at a time against `test_robustness.py` and
`test_contract_inputs.py` on this PC (CPython 3.13): P09, P10, P16, P17, P18 and P20 are
all killed.

Commit: d96a277 (contracts). Gates at d96a277 on the other machine (CPython 3.14.2, fresh
clone and venv): `ruff format --check .`, `ruff check .` and `mypy --strict src` exit 0,
and `pytest` exits 0 (751 passed, 324 skipped: the optional sources, oracles and e2e
switches are off in the default run). `mypy --strict tests` is clean on this PC.

### Round 4 (at 31cc7a0): lens e, 5 findings, all fixed

Lens e re-verified E1 to E6 as fixed (P09, P10, P16, P17, P18 and P20 killed) and ran 34
new probes; 12 survived, grouped into five findings. All five were gaps in the tests, not
wrong behaviour: on the round 3 code each repro already gives the documented error. No
library code and no CHANGELOG entry changed. None was disputed.

| Lens / id | Finding | Fix | Contract |
| --- | --- | --- | --- |
| e R4-1 (Q27, Q30) | A `RangeDecision` range or `BytePart` content range with the right fields but the wrong type was untested | Named tuples with those fields are refused | `test_range_decision_refuses_a_byte_range_lookalike`, `test_byte_part_refuses_a_content_range_lookalike` |
| e R4-2 (Q17, Q28) | No test put a wrong item after a valid one | The bad item comes second in both tests | `test_range_request_checks_every_spec_not_only_the_first`, `test_range_decision_checks_every_range_not_only_the_first` |
| e R4-3 (Q20) | `RangeRequest.other` item types were not pinned | A non-str item raises `MalformedRange`; a str subclass is stored as a plain str | `test_range_request_refuses_a_non_str_other_item`, `test_range_request_stores_other_items_as_plain_str` |
| e R4-4 (Q21 to Q26) | The 40-character type-name cut was pinned only in `_wrong` | One parametrized test over the eleven entry points that report a type: every message ends in 40 characters of the name and never holds 41 | `test_every_type_error_cuts_a_huge_type_name` |
| e R4-5 (Q03) | The name in wrong-type messages was not pinned against the qualified name | A class defined inside a function is reported by its plain name | `test_a_type_error_names_the_class_not_its_qualified_name` |

All in `tests/test_contract_item_types.py`. Mutation check of this round, one mutant at a
time against that file on this PC (CPython 3.13): Q03, Q17, Q20, Q21 to Q28 and Q30 are
all killed.

Commit: the commit that adds `tests/test_contract_item_types.py`. Gates on that tree on the
other machine (CPython 3.14.2, fresh venv): `ruff format --check .`, `ruff check .`,
`mypy --strict src`, `mypy --strict tests` and `pytest` (with `--timeout 300`) all exit 0.

### Disputed findings

None in round 1. None in round 2. None in round 3. None in round 4.

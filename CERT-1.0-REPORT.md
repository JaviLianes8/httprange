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
- [ ] Five QA lenses report PASS (item 19)
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

Pending: run by fresh agents after this preparation stage.

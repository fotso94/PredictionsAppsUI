"""
Tests for scripts/test_evidence.py, on synthetic reports only.

No real suite runs here: every Playwright report is built by hand to the shape Playwright 1.63
writes, and the pytest report and console are copied from a five-second run of eight throwaway
tests (pass, fail, skip, xfail, xpass, a setup error and two teardown errors). The guard tests
start two short-lived dummy processes whose command lines only look like a test runner and an
@playwright/mcp server.

Run from the repository root:
    backend/venv311/bin/python -m pytest scripts/tests -o addopts="" -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "test_evidence.py"
_spec = importlib.util.spec_from_file_location("test_evidence", SCRIPT)
te = importlib.util.module_from_spec(_spec)
sys.modules["test_evidence"] = te
_spec.loader.exec_module(te)

ROOT = "/Users/someone/Projects/PredictionsAppsUI"
HOME = "/Users/someone"
#: Header {"alg":"HS256","typ":"JWT"}, payload {"sub":"1234567890","role":"expert"}, a made-up signature.
FAKE_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwicm9sZSI6ImV4cGVydCJ9."
            "c2lnbmF0dXJlLXZhbHVlLWhlcmUtMTIz")


# ----------------------------------------------------------------------------- synthetic Playwright reports
def pw_test(project, expected, statuses, outcome, annotations=(), error=None):
    results = []
    for status in statuses:
        errors = [{"message": error}] if error and status in ("failed", "timedOut", "interrupted") else []
        results.append({"status": status, "errors": errors, "annotations": [], "retry": len(results)})
    return {"expectedStatus": expected, "projectName": project, "results": results,
            "annotations": list(annotations), "status": outcome}


def pw_cases(project="mocked-desktop"):
    """One test per bucket rule of Playwright's human summary, plus the extra did-not-run shape."""
    return [
        ("passes", pw_test(project, "passed", ["passed"], "expected")),
        ("fails", pw_test(project, "passed", ["failed"], "unexpected",
                          error="Error: expect(received).toBe(expected)\n"
                                f"    at {ROOT}/frontend/e2e/mocked/a.spec.ts:11:3")),
        ("flaky", pw_test(project, "passed", ["failed", "passed"], "flaky", error="Error: first try")),
        ("skipped on purpose", pw_test(project, "skipped", ["skipped"], "skipped",
                                       annotations=[{"type": "skip", "description": "needs two upcoming fixtures"}])),
        ("never started", pw_test(project, "passed", [], "skipped")),
        ("skipped after a serial failure", pw_test(project, "passed", ["skipped"], "skipped")),
        ("interrupted", pw_test(project, "passed", ["interrupted"], "skipped", error="Error: Test was interrupted.")),
    ]


def pw_report(project="mocked-desktop", cases=None):
    cases = cases if cases is not None else pw_cases(project)
    specs = [{"title": title, "file": "mocked/a.spec.ts", "line": 10 + i, "column": 3, "tests": [test]}
             for i, (title, test) in enumerate(cases)]
    counts = {"expected": 0, "unexpected": 0, "flaky": 0, "skipped": 0}
    for _, test in cases:
        counts[test["status"]] += 1
    group = {"title": "group", "file": "mocked/a.spec.ts", "line": 3, "column": 1, "specs": specs}
    return {"config": {"version": "1.63.0", "rootDir": f"{ROOT}/frontend/e2e"},
            "suites": [{"title": "mocked/a.spec.ts", "file": "mocked/a.spec.ts", "line": 0, "column": 0, "specs": [],
                        "suites": [group]}],
            "errors": [], "stats": {"startTime": "2026-10-07T02:00:00.000Z", "duration": 3100.0, **counts}}


def pw_junit(project="mocked-desktop"):
    """The JUnit Playwright writes for pw_cases(): failure for the failed test, <skipped/> for the
    four skipped-like ones, nothing for passed and flaky."""
    cases = [
        ("passes", ""),
        ("fails", '<failure message="a.spec.ts:11:3 fails" type="FAILURE">'
                  f"at {ROOT}/frontend/e2e/mocked/a.spec.ts:11:3</failure>"),
        ("flaky", ""),
        ("skipped on purpose", '<properties><property name="skip" value="needs two upcoming fixtures"></property>'
                               "</properties><skipped></skipped>"),
        ("never started", "<skipped></skipped>"),
        ("skipped after a serial failure", "<skipped></skipped>"),
        ("interrupted", "<skipped></skipped>"),
    ]
    body = "\n".join(f'<testcase name="[{project}] group &#8250; {name}" classname="mocked/a.spec.ts" '
                     f'time="0.5">{inner}</testcase>' for name, inner in cases)
    return (f'<testsuites id="" name="playwright-{project}" tests="7" failures="1" skipped="4" errors="0" time="3.1">\n'
            f'<testsuite name="mocked/a.spec.ts" timestamp="2026-10-07T02:00:00.000Z" hostname="{project}" tests="7" '
            f'failures="1" skipped="4" time="3.5" errors="0">\n{body}\n</testsuite>\n</testsuites>\n')


def pw_console(project="mocked-desktop"):
    return f"""
Running 7 tests using 1 worker

  ✓  1 [{project}] › mocked/a.spec.ts:10:3 › group › passes (1.0s)
[journey-proof] spend counters
  9 passed
  ✘  2 [{project}] › mocked/a.spec.ts:11:3 › group › fails (1.0s)
  ✓  3 [{project}] › mocked/a.spec.ts:12:3 › group › flaky (1.0s)
  -  4 [{project}] › mocked/a.spec.ts:13:3 › group › skipped on purpose

  1) [{project}] › mocked/a.spec.ts:11:3 › group › fails ───────────────

    Error: expect(received).toBe(expected)

  1 failed
    [{project}] › mocked/a.spec.ts:11:3 › group › fails ────────────────────
  1 interrupted
    [{project}] › mocked/a.spec.ts:16:3 › group › interrupted ─────────────
  1 flaky
    [{project}] › mocked/a.spec.ts:12:3 › group › flaky ───────────────────
  1 skipped
  2 did not run
  1 passed (3.1s)
"""


# ----------------------------------------------------------------------------- a real pytest report
#: pytest writes its JUnit on one line. From the real file, the hostname, the skip's reason and its
#: absolute path were changed and the error bodies shortened; the structure is untouched.
PYTEST_JUNIT = f"""<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="backend" errors="3" failures="2" skipped="2" tests="9" time="0.022" timestamp="2026-10-06T21:37:47.457944" hostname="Stephanes-MacBook-Pro"><testcase classname="test_sample" name="test_pass" time="0.000" /><testcase classname="test_sample" name="test_fail" time="0.000"><failure message="assert 1 == 2">def test_fail():
&gt;       assert 1 == 2
E       assert 1 == 2

test_sample.py:7: AssertionError</failure></testcase><testcase classname="test_sample" name="test_skip" time="0.000"><skipped type="pytest.skip" message="needs the archive">{ROOT}/backend/tests/test_sample.py:10: needs the archive</skipped></testcase><testcase classname="test_sample" name="test_xfail" time="0.000"><skipped type="pytest.xfail" message="known" /></testcase><testcase classname="test_sample" name="test_xpass" time="0.000" /><testcase classname="test_sample" name="test_setup_error" time="0.000"><error message="failed on setup with &quot;RuntimeError: setup boom&quot;">test_sample.py:22: RuntimeError</error></testcase><testcase classname="test_sample" name="test_teardown_error_after_pass" time="0.000"><error message="failed on teardown with &quot;RuntimeError: teardown boom&quot;">test_sample.py:30: RuntimeError</error></testcase><testcase classname="test_sample" name="test_teardown_error_after_fail" time="0.000"><failure message="assert 0">test_sample.py:36: AssertionError</failure></testcase><testcase classname="test_sample" name="test_teardown_error_after_fail" time="0.000"><error message="failed on teardown with &quot;RuntimeError: teardown boom&quot;">test_sample.py:30: RuntimeError</error></testcase></testsuite></testsuites>"""  # noqa: E501

PYTEST_CONSOLE = f""".FsxXE.EFE                                                               [100%]
==================================== ERRORS ====================================
______________________ ERROR at setup of test_setup_error ______________________
E       RuntimeError: setup boom
- generated xml file: {ROOT}/.test-runs/run/backend.junit.xml -
=========================== short test summary info ============================
FAILED test_sample.py::test_fail - assert 1 == 2
FAILED test_sample.py::test_teardown_error_after_fail - assert 0
ERROR test_sample.py::test_setup_error - RuntimeError: setup boom
ERROR test_sample.py::test_teardown_error_after_pass - RuntimeError: teardown...
ERROR test_sample.py::test_teardown_error_after_fail - RuntimeError: teardown...
SKIPPED [1] test_sample.py:10: needs the archive
2 failed, 2 passed, 1 skipped, 1 xfailed, 1 xpassed, 3 errors in 0.02s
"""


def unreachable(junit: str) -> str:
    return junit.replace('message="needs the archive"', 'message="PostgreSQL test database not reachable: refused"')


#: An all-green backend run, for the runs whose only failure is somewhere else.
PASSING_PYTEST_JUNIT = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="backend" errors="0" '
                        'failures="0" skipped="0" tests="3" time="0.1" timestamp="2026-10-07T02:00:00" hostname="h">'
                        '<testcase classname="t" name="a" time="0"/><testcase classname="t" name="b" time="0"/>'
                        '<testcase classname="t" name="c" time="0"/></testsuite></testsuites>')
PASSING_PYTEST_CONSOLE = "..." + " " * 70 + "[100%]\n3 passed in 0.10s\n"


def pw_passing(project):
    """(console, JSON report, JUnit) of a Playwright project whose two tests both passed."""
    cases = [("passes", pw_test(project, "passed", ["passed"], "expected")),
             ("also passes", pw_test(project, "passed", ["passed"], "expected"))]
    body = "\n".join(f'<testcase name="[{project}] group &#8250; {name}" classname="mocked/a.spec.ts" time="0.5">'
                     "</testcase>" for name, _ in cases)
    junit = (f'<testsuites id="" name="playwright-{project}" tests="2" failures="0" skipped="0" errors="0" time="1">\n'
             f'<testsuite name="mocked/a.spec.ts" timestamp="2026-10-07T02:00:00.000Z" hostname="{project}" tests="2" '
             f'failures="0" skipped="0" time="1" errors="0">\n{body}\n</testsuite>\n</testsuites>\n')
    console = (f"\nRunning 2 tests using 1 worker\n\n"
               f"  ✓  1 [{project}] › mocked/a.spec.ts:10:3 › group › passes (0.5s)\n"
               f"  ✓  2 [{project}] › mocked/a.spec.ts:11:3 › group › also passes (0.5s)\n\n  2 passed (1.0s)\n")
    return console, pw_report(project, cases), junit


# ----------------------------------------------------------------------------- Playwright buckets
EVERY_BUCKET = {"passed": 1, "failed": 1, "flaky": 1, "skipped": 1, "did_not_run": 2, "interrupted": 1}


def test_json_buckets_follow_the_human_summary_rules():
    analysis = te.analyse_playwright_json(pw_report())
    assert analysis["buckets"] == EVERY_BUCKET
    assert analysis["total"] == 7
    assert analysis["status_disagreements"] == 0
    assert analysis["projects"] == ["mocked-desktop"]
    # The JSON's own stats fold did-not-run and interrupted into "skipped": four, not one.
    assert analysis["stats"]["skipped"] == 4


def test_each_bucket_rule_on_its_own():
    cases = dict(pw_cases())
    assert te.human_bucket(cases["passes"]) == "passed"
    assert te.human_bucket(cases["fails"]) == "failed"
    assert te.human_bucket(cases["flaky"]) == "flaky"
    assert te.human_bucket(cases["skipped on purpose"]) == "skipped"
    assert te.human_bucket(cases["never started"]) == "did_not_run"
    assert te.human_bucket(cases["skipped after a serial failure"]) == "did_not_run"
    assert te.human_bucket(cases["interrupted"]) == "interrupted"


def test_an_outcome_that_disagrees_with_its_results_is_counted():
    cases = pw_cases()
    cases[0][1]["status"] = "skipped"   # a "skipped" label on a test whose only result passed
    assert te.analyse_playwright_json(pw_report(cases=cases))["status_disagreements"] == 1


def test_skip_reasons_and_failure_lines_are_collected():
    analysis = te.analyse_playwright_json(pw_report())
    reasons = {t["title"]: t["reason"] for t in analysis["skipped_tests"]}
    assert reasons["group > skipped on purpose"] == "needs two upcoming fixtures"
    assert {t["bucket"] for t in analysis["skipped_tests"]} == {"skipped", "did_not_run", "interrupted"}
    failed = [f for f in analysis["failures"] if f["bucket"] == "failed"]
    assert failed[0]["error"] == "Error: expect(received).toBe(expected)"
    assert failed[0]["location"] == "mocked/a.spec.ts:11"


def test_human_summary_is_read_from_the_epilogue_only():
    parsed = te.parse_playwright_console(pw_console())
    assert parsed["planned"] == 7 and parsed["workers"] == 1
    # "  9 passed" printed by a test in the middle of the run is not the summary.
    assert parsed["buckets"] == EVERY_BUCKET
    assert parsed["lines"][0] == "  1 failed" and parsed["lines"][-1] == "  1 passed (3.1s)"


def test_errors_outside_tests_are_read():
    head, tail = "Running 1 test using 1 worker\n\n", "\n  1 passed (1.0s)\n"
    parsed = te.parse_playwright_console(head + "  1 error was not a part of any test, see above for details" + tail)
    assert parsed["fatal_errors"] == 1
    parsed = te.parse_playwright_console(head + "  3 errors were not a part of any test, see above" + tail)
    assert parsed["fatal_errors"] == 3


def test_a_console_without_a_summary_has_no_buckets():
    parsed = te.parse_playwright_console("Error: No tests found.\n")
    assert parsed["buckets"] is None and parsed["planned"] is None


def test_playwright_junit_totals():
    junit = te.analyse_playwright_junit(pw_junit())
    assert (junit["tests"], junit["failures"], junit["errors"], junit["skipped"], junit["passed"]) == (7, 1, 0, 4, 2)
    assert junit["projects"] == ["mocked-desktop"]
    assert junit["consistent"]


def test_playwright_junit_whose_stated_totals_lie_is_inconsistent():
    stated = 'tests="7" failures="1" skipped="4" errors="0" time="3.1"'
    lying = pw_junit().replace(stated, stated.replace('failures="1"', 'failures="0"'))
    assert not te.analyse_playwright_junit(lying)["consistent"]


def write_playwright_raw(raw: Path, project="mocked-desktop", console=None, report=None, junit=None):
    console = console if console is not None else pw_console(project)
    report = report if report is not None else pw_report(project)
    junit = junit if junit is not None else pw_junit(project)
    (raw / f"playwright-{project}.console.log").write_text(console, encoding="utf-8")
    (raw / f"playwright-{project}.json").write_text(json.dumps(report), encoding="utf-8")
    (raw / f"playwright-{project}.junit.xml").write_text(junit, encoding="utf-8")


def test_human_json_and_junit_agree(tmp_path):
    write_playwright_raw(tmp_path)
    analysis = te.analyse_playwright("mocked-desktop", tmp_path, {"exit_code": 1, "interrupted": False}, False)
    failing = [c for c in analysis["checks"] if not c["ok"]]
    assert failing == []
    assert analysis["planned"] == 7


def test_a_human_summary_that_disagrees_with_the_json_is_not_evidence(tmp_path):
    write_playwright_raw(tmp_path, console=pw_console().replace("  1 passed (3.1s)", "  2 passed (3.1s)")
                         .replace("Running 7 tests", "Running 8 tests"))
    suite = {"status": "ran", "exit_code": 1,
             **te.analyse_playwright("mocked-desktop", tmp_path, {"exit_code": 1, "interrupted": False}, False)}
    failing = {c["name"] for c in suite["checks"] if not c["ok"]}
    assert "human passed = JSON" in failing
    assert te.suite_verdict(suite) == "NOT EVIDENCE"


def test_a_report_for_another_project_is_not_evidence(tmp_path):
    write_playwright_raw(tmp_path, report=pw_report("mocked-mobile"), junit=pw_junit("mocked-mobile"))
    analysis = te.analyse_playwright("mocked-desktop", tmp_path, {"exit_code": 1, "interrupted": False}, False)
    failing = {c["name"] for c in analysis["checks"] if not c["ok"]}
    assert {"JSON holds exactly the requested project", "JUnit holds exactly the requested project"} <= failing


def test_exit_zero_with_a_failure_is_not_evidence(tmp_path):
    write_playwright_raw(tmp_path)
    analysis = te.analyse_playwright("mocked-desktop", tmp_path, {"exit_code": 0, "interrupted": False}, False)
    assert {c["name"] for c in analysis["checks"] if not c["ok"]} == {"exit code agrees with the results"}


# ----------------------------------------------------------------------------- pytest
def test_pytest_junit_counts_like_pytest_does():
    junit = te.analyse_pytest_junit(PYTEST_JUNIT)
    # pytest said: 2 failed, 2 passed, 1 skipped, 1 xfailed, 1 xpassed, 3 errors
    counted = (junit["failed"], junit["errors"], junit["skipped"], junit["xfailed"], junit["passed_or_xpassed"])
    assert counted == (2, 3, 1, 1, 3)
    assert junit["testcases"] == 9 and junit["consistent"]
    assert junit["skips"] == [{"test": "test_sample::test_skip", "location": f"{ROOT}/backend/tests/test_sample.py:10",
                               "reason": "needs the archive"}]


@pytest.mark.parametrize("line, expected", [
    ("2 failed, 2 passed, 1 skipped, 1 xfailed, 1 xpassed, 3 errors in 0.02s",
     {"failed": 2, "passed": 2, "skipped": 1, "xfailed": 1, "xpassed": 1, "errors": 3}),
    ("========= 1 failed, 1400 passed, 14 skipped, 2 warnings in 312.41s (0:05:12) =========",
     {"failed": 1, "passed": 1400, "skipped": 14, "warnings": 2}),
    ("1 passed, 1 error in 0.10s", {"passed": 1, "errors": 1}),
    ("no tests ran in 0.01s", {}),
])
def test_pytest_final_line(line, expected):
    parsed = te.parse_pytest_console("collected\n" + line + "\n")
    assert parsed["line"] == line
    assert {k: v for k, v in parsed["counts"].items() if v} == expected


def test_backend_report_that_agrees(tmp_path):
    (tmp_path / "backend.console.log").write_text(PYTEST_CONSOLE, encoding="utf-8")
    (tmp_path / "backend.junit.xml").write_text(PYTEST_JUNIT, encoding="utf-8")
    analysis = te.analyse_backend(tmp_path, {"exit_code": 1, "interrupted": False}, False)
    assert [c for c in analysis["checks"] if not c["ok"]] == []


def test_backend_skip_saying_not_reachable_is_not_evidence(tmp_path):
    (tmp_path / "backend.console.log").write_text(PYTEST_CONSOLE, encoding="utf-8")
    (tmp_path / "backend.junit.xml").write_text(unreachable(PYTEST_JUNIT), encoding="utf-8")
    analysis = te.analyse_backend(tmp_path, {"exit_code": 1, "interrupted": False}, False)
    suite = {"status": "ran", "exit_code": 1, **analysis}
    failing = [c["name"] for c in suite["checks"] if not c["ok"]]
    assert failing == ["no skip says the test database or Redis is not reachable"]
    assert te.suite_verdict(suite) == "NOT EVIDENCE"


def test_a_backend_run_that_collected_nothing_is_not_evidence(tmp_path):
    (tmp_path / "backend.console.log").write_text("\nno tests ran in 0.01s\n", encoding="utf-8")
    (tmp_path / "backend.junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="backend" errors="0" failures="0" '
        'skipped="0" tests="0" time="0.010" timestamp="2026-10-06T21:37:47" hostname="h" /></testsuites>',
        encoding="utf-8")
    analysis = te.analyse_backend(tmp_path, {"exit_code": 5, "interrupted": False}, False)
    suite = {"status": "ran", "exit_code": 5, **analysis}
    assert [c["name"] for c in suite["checks"] if not c["ok"]] == ["at least one test ran"]
    assert te.suite_verdict(suite) == "NOT EVIDENCE"


def test_backend_without_a_summary_line_is_not_evidence(tmp_path):
    (tmp_path / "backend.console.log").write_text("Traceback (most recent call last):\n", encoding="utf-8")
    (tmp_path / "backend.junit.xml").write_text(PYTEST_JUNIT, encoding="utf-8")
    analysis = te.analyse_backend(tmp_path, {"exit_code": 1, "interrupted": False}, False)
    assert "pytest summary line present" in [c["name"] for c in analysis["checks"] if not c["ok"]]


# ----------------------------------------------------------------------------- verdicts
def test_verdicts():
    passing = {"status": "ran", "exit_code": 0, "checks": [{"name": "x", "ok": True}]}
    failing = {"status": "ran", "exit_code": 1, "checks": [{"name": "x", "ok": True}]}
    broken = {"status": "ran", "exit_code": 0, "checks": [{"name": "x", "ok": False}]}
    assert te.suite_verdict(passing) == "PASS"
    assert te.suite_verdict(failing) == "FAIL"
    assert te.suite_verdict(broken) == "NOT EVIDENCE"
    assert te.suite_verdict({"status": "not run"}) == "NOT RUN"
    assert te.overall_verdict({"suites": [passing]}) == "PASS"
    assert te.overall_verdict({"suites": [passing, failing]}) == "FAIL"
    assert te.overall_verdict({"suites": [failing, broken]}) == "NOT EVIDENCE"
    assert te.overall_verdict({"suites": [passing], "partial": True}) == "NOT EVIDENCE"
    assert te.overall_verdict({"suites": [passing], "interrupted": True}) == "NOT EVIDENCE"
    restarted = {"anomalies": [{"kind": "server_restart"}]}
    assert te.overall_verdict({"suites": [passing], "watcher": restarted}) == "CONTAMINATED"


# ----------------------------------------------------------------------------- scrubbing
def scrubber():
    return te.Scrubber([ROOT, f"{ROOT}/.claude/worktrees/stoic"], HOME)


def test_scrub_paths():
    s = scrubber()
    text = (f"at {ROOT}/frontend/e2e/live/a.spec.ts:10\n"
            f"worktree {ROOT}/.claude/worktrees/stoic/backend/tests/x.py:3\n"
            f"browsers in {HOME}/Library/Caches/ms-playwright\n")
    out = s.scrub(text, "t.txt")
    assert out == ("at <repo>/frontend/e2e/live/a.spec.ts:10\n"
                   "worktree <repo>/backend/tests/x.py:3\n"
                   "browsers in ~/Library/Caches/ms-playwright\n")
    assert s.counts["t.txt"] == {"repo-root": 2, "home": 1}


def test_a_path_under_another_user_aborts_without_naming_it():
    with pytest.raises(te.ScrubAbort) as caught:
        scrubber().scrub("line one\nopened /Users/otherperson/secret-project/x\n", "t.txt")
    assert "line 2" in str(caught.value)
    assert "otherperson" not in str(caught.value)


def test_scrub_jwt_and_bearer():
    s = scrubber()
    out = s.scrub(f"  - authorization: Bearer {FAKE_JWT}\ntoken={FAKE_JWT[:20]} body {FAKE_JWT}\n", "t.txt")
    assert FAKE_JWT not in out
    assert "authorization: Bearer <redacted>" in out
    assert "body <jwt>" in out
    assert s.counts["t.txt"] == {"bearer-header": 1, "jwt": 1}


def test_scrub_database_and_redis_urls():
    s = scrubber()
    out = s.scrub("postgresql://postgres:hunter22pw@localhost:5432/soccer_predictions_test and "
                  "postgresql+psycopg2://app:pw2@db/x and redis://:redispw@localhost:6379/0", "t.txt")
    assert out == ("postgresql://postgres:<redacted>@localhost:5432/soccer_predictions_test and "
                   "postgresql+psycopg2://app:<redacted>@db/x and redis://:<redacted>@localhost:6379/0")
    assert s.counts["t.txt"] == {"url-credentials": 3}


def test_scrub_secret_query_parameters_in_text_and_xml():
    s = scrubber()
    url = "https://livescore-api.com/api-client/fixtures/list.json?key=abc123&secret=def456&competition_id=2"
    assert s.scrub(url, "t.txt") == ("https://livescore-api.com/api-client/fixtures/list.json?key=<redacted>"
                                     "&secret=<redacted>&competition_id=2")
    xml_text = f'<failure message="GET {url.replace("&", "&amp;")}">x</failure>'
    out = s.scrub(xml_text, "t.xml", xml=True)
    assert "abc123" not in out and "def456" not in out
    assert ET.fromstring(out).get("message").endswith("?key=<redacted>&secret=<redacted>&competition_id=2")


def test_scrub_is_idempotent():
    s = scrubber()
    once = s.scrub(f"{ROOT}/x authorization: Bearer {FAKE_JWT} ?key=abc postgresql://u:p@h/db", "t.txt")
    counts = dict(s.counts["t.txt"])
    assert s.scrub(once, "t.txt") == once
    assert s.counts["t.txt"] == counts


def test_emails_outside_the_allowed_domains_abort():
    s = scrubber()
    kept = "qa.expert@predictions-local.dev wrote to owner@example.com about icon@2x.png"
    assert s.scrub(kept, "t.txt") == kept
    with pytest.raises(te.ScrubAbort) as caught:
        s.scrub("ok\nreply to someone.private@gmail.com\n", "t.txt")
    assert "gmail.com" in str(caught.value) and "line 2" in str(caught.value)
    assert "someone.private" not in str(caught.value)


def test_pytest_hostname_is_redacted_and_the_xml_stays_well_formed():
    s = scrubber()
    out = s.scrub(PYTEST_JUNIT, "backend.junit.xml", xml=True, pytest_junit=True)
    assert "Stephanes-MacBook-Pro" not in out
    root = ET.fromstring(out)
    assert root.find("testsuite").get("hostname") == "<redacted>"
    skip = root.find(".//skipped[@type='pytest.skip']")
    assert skip.text.startswith("<repo>/backend/tests/test_sample.py:10")
    assert s.counts["backend.junit.xml"] == {"pytest-hostname": 1, "repo-root": 1}


def test_playwright_hostname_is_the_project_and_is_kept():
    out = scrubber().scrub(pw_junit(), "p.xml", xml=True)
    assert ET.fromstring(out).find("testsuite").get("hostname") == "mocked-desktop"


def test_ansi_is_stripped():
    assert scrubber().scrub("\x1b[31m  1 failed\x1b[39m", "t.txt") == "  1 failed"


# ----------------------------------------------------------------------------- deny-list
def test_deny_list_reads_env_files_and_never_shows_values(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text('SECRET_KEY="super-secret-signing-key"\nSMTP_USER=abc\nLIVESCORE_API_SECRET=ls-secret-value-9\n'
                   "DEBUG=true\n# GAMEFORECAST_API_KEY=commented-out-value\nexport SMTP_PASSWORD='smtp-pass-12345' \n",
                   encoding="utf-8")
    deny, too_short = te.load_deny_list([("backend/.env", env)], {"E2E_QA_PASSWORD": "qa-override-pw"},
                                        {"hostname": "Mac"})
    assert set(deny) == {"SECRET_KEY (backend/.env)", "LIVESCORE_API_SECRET (backend/.env)",
                         "SMTP_PASSWORD (backend/.env)", "E2E_QA_PASSWORD (environment)"}
    assert too_short == ["SMTP_USER (backend/.env)", "hostname"]
    text = "ok\nthe signing key is super-secret-signing-key\n<x a=\"smtp-pass-12345\"/>\n"
    findings = te.leak_scan(text, "summary.md", deny)
    assert findings == ["summary.md: line 2: the value of SECRET_KEY (backend/.env)",
                        "summary.md: line 3: the value of SMTP_PASSWORD (backend/.env)"]
    joined = "\n".join(findings) + capsys.readouterr().out
    for value in ("super-secret-signing-key", "smtp-pass-12345", "ls-secret-value-9", "qa-override-pw"):
        assert value not in joined


def test_deny_list_finds_xml_and_url_encoded_forms():
    deny = {"SMTP_PASSWORD (backend/.env)": "p&ss<word>/x"}
    found = "line 1: the value of SMTP_PASSWORD (backend/.env)"
    assert te.leak_scan('<a v="p&amp;ss&lt;word&gt;/x"/>', "a.xml", deny) == [f"a.xml: {found}"]
    assert te.leak_scan("?q=p%26ss%3Cword%3E%2Fx", "a.txt", deny) == [f"a.txt: {found}"]


def test_leak_scan_flags_what_the_scrub_would_have_rewritten():
    text = f"/Users/x/y\nBearer {FAKE_JWT}\npostgresql://u:pw@h/db\n?token=abc\nme@gmail.com\n"
    findings = te.leak_scan(text, "f.txt", {})
    assert findings == ["f.txt: line 1: an absolute /Users/ path", "f.txt: line 2: a JWT",
                        "f.txt: line 3: credentials in a database URL", "f.txt: line 4: a secret query parameter",
                        "f.txt: line 5: an email address at gmail.com"]


def test_committed_qa_password_is_read_from_the_spec_support_file():
    value = te.committed_qa_password()
    assert value and len(value) >= te.MIN_DENY_LENGTH


# ----------------------------------------------------------------------------- publish and verify
HEAD = "201442e" + "0" * 33


def synthetic_run(tmp_path: Path, junit=PYTEST_JUNIT, suites=te.ALL_SUITES, passing=(), grep=None,
                  backend_console=None, not_run=()):
    """A finished run, assembled the way cmd_run assembles it, from synthetic raw reports.

    Every suite fails one test and exits 1 unless it is named in `passing`. The partial reasons and
    the run id are worked out here the way Options and make_run_id do it, independently of `verify`.
    Suites named in `not_run` were never started because the run was stopped before them.
    """
    reasons = [] if tuple(suites) == te.ALL_SUITES else [f"only {', '.join(suites)} requested"]
    reasons += ["tests filtered with --grep"] if grep else []
    run_id = te.make_run_id(datetime(2026, 10, 7, 2, tzinfo=timezone.utc), HEAD, False, bool(reasons))
    raw = tmp_path / ".test-runs" / run_id
    raw.mkdir(parents=True)
    label = Path(f"{ROOT}/.test-runs/{run_id}")   # where cmd_run would have written them
    entries = []
    for name in suites:
        green = name in passing
        if name == "backend":
            console = backend_console or (PASSING_PYTEST_CONSOLE if green else PYTEST_CONSOLE)
            (raw / "backend.console.log").write_text(console, encoding="utf-8")
            (raw / "backend.junit.xml").write_text(PASSING_PYTEST_JUNIT if green else junit, encoding="utf-8")
            command = {"cwd": f"{ROOT}/backend", "env": ["PYTHONUNBUFFERED", "TEST_DATABASE_URL"],
                       "argv": [f"{ROOT}/backend/venv311/bin/python"] + te.backend_command(label, grep)[1:]}
        else:
            if green:
                write_playwright_raw(raw, name, *pw_passing(name))
            else:
                write_playwright_raw(raw, name)
            env = te.playwright_env(name, label, "http://localhost:3100", "http://127.0.0.1:8000")
            command = {"cwd": f"{ROOT}/frontend", "env": sorted(env),
                       "argv": [f"{ROOT}/frontend/node_modules/.bin/playwright"]
                       + te.playwright_command(name, label, grep)[1:]}
        entry = {"name": name, "kind": "pytest" if name == "backend" else "playwright", "files": {},
                 "command": command}
        if name in not_run:
            entry.update(status="not run", exit_code=None, checks=[], buckets={})
            entries.append(entry)
            continue
        ran = {"exit_code": 0 if green else 1, "started_at": "2026-10-07T02:00:00Z",
               "finished_at": "2026-10-07T02:01:00Z", "duration_seconds": 60.0, "interrupted": False}
        entry.update(status="ran", **ran)
        entry.update(te.analyse_backend(raw, ran, bool(reasons)) if name == "backend"
                     else te.analyse_playwright(name, raw, ran, bool(reasons)))
        entries.append(entry)
    repo = {"head": HEAD, "branch": "main", "dirty": False, "dirty_paths": [], "diff_sha256": "d",
            "untracked_sha256": "u", "origin_main": HEAD, "last_fetch_at": "2026-10-06T00:00:00Z"}
    record = {"repository": repo, "guard_at_start": [], "tools": {"node": "v24.8.0"},
              "servers": {"frontend": {"url": "http://localhost:3100", "listening": True, "pid": 44833,
                                       "started_at": "2026-10-07T01:02:46Z", "cwd": f"{ROOT}/frontend",
                                       "command": f"node {ROOT}/frontend/node_modules/.bin/vite --port 3100",
                                       "checkout": {"toplevel": ROOT, "head": repo["head"], "dirty_paths": []},
                                       "unchanged_at_end": True}}}
    summary = te.assemble_summary(run_id=raw.name, partial_reasons=reasons, interrupted=bool(not_run),
                                  started_at=datetime(2026, 10, 7, 2, tzinfo=timezone.utc),
                                  finished_at=datetime(2026, 10, 7, 2, 2, tzinfo=timezone.utc), record=record, end=repo,
                                  allow_dirty=False, suites=entries,
                                  watcher={"interval_seconds": 15, "samples": 8, "anomalies": []},
                                  lock={"path": f"{ROOT}/.git/lock", "acquired_at": "2026-10-07T02:00:00Z",
                                        "stale_lock_cleared": None})
    return summary, raw


def publish_synthetic(tmp_path: Path, deny=None, junit=PYTEST_JUNIT, **run):
    summary, raw = synthetic_run(tmp_path, junit, **run)
    out = tmp_path / "docs" / "evidence" / "test-reports" / raw.name
    public = te.publish(summary, raw, out, scrubber(), deny or {}, ["SMTP_USER (backend/.env)"])
    return public, out


def tamper(out: Path, change):
    """Edit summary.json, then do what anyone can with the script's own functions: render summary.md
    again and rewrite SHA256SUMS. Returns verify's result and its lines."""
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    change(summary)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(te.render_summary_md(summary), encoding="utf-8")
    te.write_sha256sums(out)
    lines = []
    return te.verify_dir(out, emit=lines.append), lines


def rederive_verdicts(summary):
    for suite in summary["suites"]:
        suite["verdict"] = te.suite_verdict(suite)
    summary["verdict"] = te.overall_verdict(summary)


def failed_lines(lines):
    return [line for line in lines if line.startswith("FAIL")]


def test_publish_writes_the_scrubbed_set_and_it_verifies(tmp_path, capsys):
    public, out = publish_synthetic(tmp_path)
    per_project = [f"playwright-{p}.{kind}" for p in sorted(te.PLAYWRIGHT_PROJECTS)
                   for kind in ("console-tail.txt", "junit.xml")]
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["SHA256SUMS", "backend.console-tail.txt", "backend.junit.xml", "summary.json", "summary.md"] + per_project)
    assert public["verdict"] == "FAIL"
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text and "Stephanes-MacBook-Pro" not in text
    assert public["integrity"]["scrub_counts"]["backend.junit.xml"] == {"pytest-hostname": 1, "repo-root": 1}
    assert public["integrity"]["raw_files"]["backend.junit.xml"]["sha256"] == te.sha256_bytes(PYTEST_JUNIT.encode())
    assert te.verify_dir(out) is True
    assert "VERIFIED" in capsys.readouterr().out
    # The checksum file is in the format shasum -a 256 -c reads.
    if shutil.which("shasum"):
        assert subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"], cwd=out, capture_output=True).returncode == 0


def test_verify_detects_a_tampered_total(tmp_path):
    _, out = publish_synthetic(tmp_path)
    summary = json.loads((out / "summary.json").read_text())
    summary["suites"][0]["junit"]["failed"] = 0
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    assert te.verify_dir(out, emit=lambda line: None) is False
    te.write_sha256sums(out)   # even with the checksums brought up to date
    lines = []
    assert te.verify_dir(out, emit=lines.append) is False
    assert "FAIL  backend: JUnit failed recomputed = summary.json (2)" in lines


def test_verify_detects_a_tampered_junit_file(tmp_path):
    _, out = publish_synthetic(tmp_path)
    xml_path = out / "playwright-mocked-desktop.junit.xml"
    root = ET.fromstring(xml_path.read_text())
    suite = root.find("testsuite")
    suite.remove(suite.findall("testcase")[1])   # drop the failing test
    xml_path.write_text(ET.tostring(root, encoding="unicode"))
    te.write_sha256sums(out)
    lines = []
    assert te.verify_dir(out, emit=lines.append) is False
    assert any(line.startswith("FAIL  mocked-desktop: JUnit tests recomputed") for line in lines)


def test_the_playwright_failure_count_is_published_and_verified(tmp_path):
    # pytest's analysis once kept its list of failed tests under the same key as Playwright's
    # failure count, and dropping the list before publishing dropped the count too.
    public, out = publish_synthetic(tmp_path)
    assert next(s for s in public["suites"] if s["name"] == "mocked-desktop")["junit"]["failures"] == 1
    assert "failures 1, errors 0" in (out / "summary.md").read_text()
    summary = json.loads((out / "summary.json").read_text())
    summary["suites"][1]["junit"]["failures"] = 0
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "summary.md").write_text(te.render_summary_md(summary))
    te.write_sha256sums(out)
    lines = []
    assert te.verify_dir(out, emit=lines.append) is False
    assert "FAIL  mocked-desktop: JUnit failures recomputed = summary.json (1)" in lines


def test_verify_detects_a_changed_checksum_an_extra_file_and_an_edited_summary_md(tmp_path):
    _, out = publish_synthetic(tmp_path)
    (out / "backend.console-tail.txt").write_text("edited\n")
    (out / "notes.txt").write_text("extra\n")
    with open(out / "summary.md", "a", encoding="utf-8") as handle:
        handle.write("\nAll green!\n")
    lines = []
    assert te.verify_dir(out, emit=lines.append) is False
    assert "FAIL  backend.console-tail.txt matches SHA256SUMS" in lines
    assert any(line.startswith("FAIL  every file is listed in SHA256SUMS") for line in lines)
    assert "FAIL  summary.md is exactly what summary.json renders to" in lines


def test_verify_detects_a_flipped_verdict(tmp_path):
    _, out = publish_synthetic(tmp_path)
    summary = json.loads((out / "summary.json").read_text())
    summary["verdict"] = "PASS"
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "summary.md").write_text(te.render_summary_md(summary))
    te.write_sha256sums(out)
    lines = []
    assert te.verify_dir(out, emit=lines.append) is False
    assert "FAIL  overall verdict PASS follows from the suites and the watcher" in lines


def test_a_missing_junit_report_publishes_as_not_evidence_and_still_verifies(tmp_path):
    summary, raw = synthetic_run(tmp_path)
    (raw / "playwright-mocked-desktop.junit.xml").unlink()
    playwright = summary["suites"][1]
    playwright.update(te.analyse_playwright("mocked-desktop", raw, {"exit_code": 1, "interrupted": False}, False))
    playwright["verdict"] = te.suite_verdict(playwright)
    summary["verdict"] = te.overall_verdict(summary)
    out = tmp_path / "published"
    public = te.publish(summary, raw, out, scrubber(), {}, [])
    assert public["verdict"] == "NOT EVIDENCE"
    assert "playwright-mocked-desktop.junit.xml" not in os.listdir(out)
    lines = []
    assert te.verify_dir(out, emit=lines.append) is True, failed_lines(lines)
    assert "ok    mocked-desktop: no JUnit file published, and summary.json records none" in lines
    assert "ok    mocked-desktop: 'JUnit report present and parseable' recomputes as FAILED, as recorded" in lines


# Each of the next three starts from an honest publish and edits only summary.json, then renders
# summary.md again and rewrites SHA256SUMS with the script's own functions. Before `verify`
# recomputed these fields, each edit verified, and the edited summary read PASS.
def test_verify_recomputes_the_exit_code_check_instead_of_trusting_it(tmp_path):
    public, out = publish_synthetic(tmp_path)
    assert public["verdict"] == "FAIL"

    def exits_zero(summary):
        for suite in summary["suites"]:
            suite["exit_code"] = 0
        rederive_verdicts(summary)
        assert summary["verdict"] == "PASS"   # what the edit is after

    ok, lines = tamper(out, exits_zero)
    assert ok is False
    assert "FAIL  backend: 'exit code agrees with the results' recomputes as FAILED, as recorded" in lines
    assert "FAIL  mocked-desktop: 'exit code agrees with the results' recomputes as FAILED, as recorded" in lines
    # The published JUnit still holds the failures the edit tried to hide.
    assert (out / "backend.junit.xml").read_text(encoding="utf-8").count("<failure") == 2


def test_verify_rejects_a_full_run_with_a_suite_dropped(tmp_path):
    green = ("backend", "mocked-mobile", "mocked-mobile-360", "live", "live-isolated")
    public, out = publish_synthetic(tmp_path, passing=green)
    assert public["verdict"] == "FAIL"
    assert te.verify_dir(out, emit=lambda line: None) is True
    for name in ("playwright-mocked-desktop.junit.xml", "playwright-mocked-desktop.console-tail.txt"):
        (out / name).unlink()

    def drop_the_failing_suite(summary):
        summary["suites"] = [s for s in summary["suites"] if s["name"] != "mocked-desktop"]
        integrity = summary["integrity"]
        for key in ("published_sha256", "raw_files"):
            integrity[key] = {k: v for k, v in integrity[key].items() if "mocked-desktop" not in k}
        rederive_verdicts(summary)
        assert summary["verdict"] == "PASS"

    ok, lines = tamper(out, drop_the_failing_suite)
    assert ok is False
    assert any(line.startswith("FAIL  the run is partial, as recorded") for line in lines), failed_lines(lines)
    assert "FAIL  the run id ends in -partial exactly when the run is partial" in lines


def test_verify_rejects_a_filtered_run_relabelled_as_a_full_one(tmp_path):
    public, out = publish_synthetic(tmp_path, suites=("backend",), passing=("backend",), grep="parlay",
                                    backend_console="...  [100%]\n3 passed, 1606 deselected in 0.10s\n")
    assert public["verdict"] == "NOT EVIDENCE" and public["run_id"].endswith("-partial")
    assert te.verify_dir(out, emit=lambda line: None) is True

    def not_partial(summary):
        summary["partial"] = False
        summary["partial_reasons"] = []
        rederive_verdicts(summary)
        assert summary["verdict"] == "PASS"

    ok, lines = tamper(out, not_partial)
    assert ok is False
    assert any(line.startswith("FAIL  the run is partial, as recorded") for line in lines), failed_lines(lines)
    assert "FAIL  the run id ends in -partial exactly when the run is partial" not in lines   # it still does


def test_verify_rejects_a_filter_removed_from_the_command(tmp_path):
    # A full run filtered with -k, whose filter and "-partial" were edited out: the backend's
    # "nothing deselected" check, which only a full run makes, is recomputed and fails.
    _, out = publish_synthetic(tmp_path, grep="parlay", passing=te.ALL_SUITES,
                               backend_console="...  [100%]\n3 passed, 1606 deselected in 0.10s\n")

    def unfiltered(summary):
        for suite in summary["suites"]:
            argv = suite["command"]["argv"]
            flag = argv.index("-k" if suite["kind"] == "pytest" else "--grep")
            del argv[flag:flag + 2]
        summary["partial"], summary["partial_reasons"] = False, []
        summary["run_id"] = summary["run_id"][:-len("-partial")]
        rederive_verdicts(summary)
        assert summary["verdict"] == "PASS"

    ok, lines = tamper(out, unfiltered)
    assert ok is False
    assert any(line.startswith("FAIL  backend: the recorded checks are the ones the run makes") for line in lines)


def test_verify_rejects_a_command_the_runner_does_not_build(tmp_path):
    _, out = publish_synthetic(tmp_path)

    def stop_at_the_first_failure(summary):
        summary["suites"][0]["command"]["argv"].append("-x")

    ok, lines = tamper(out, stop_at_the_first_failure)
    assert ok is False
    assert "FAIL  backend: the command is the one the runner builds for it" in lines


def test_verify_reads_the_reporters_summary_back_from_the_console_tail(tmp_path):
    # Moving one test from "skipped" to "did not run" changes no JUnit total and no JSON stat, so
    # only the published console tail can show that the reporter said otherwise.
    _, out = publish_synthetic(tmp_path)

    def move_a_skip(summary):
        suite = summary["suites"][1]
        for buckets in (suite["buckets"], suite["human"]["buckets"], suite["json"]["buckets"]):
            buckets["skipped"], buckets["did_not_run"] = 2, 1
        suite["human"]["lines"] = [{"  1 skipped": "  2 skipped", "  2 did not run": "  1 did not run"}.get(line, line)
                                   for line in suite["human"]["lines"]]

    ok, lines = tamper(out, move_a_skip)
    assert ok is False
    assert len(failed_lines(lines)) == 1, failed_lines(lines)
    assert failed_lines(lines)[0].startswith("FAIL  mocked-desktop: the published console tail holds the same summary")


def test_verify_rejects_buckets_that_are_not_the_reporters_own(tmp_path):
    _, out = publish_synthetic(tmp_path)

    def edit_the_summary_line(summary):
        human = summary["suites"][0]["human"]
        human["line"] = human["line"].replace("3 errors", "4 errors")

    ok, lines = tamper(out, edit_the_summary_line)
    assert ok is False
    failed = failed_lines(lines)
    assert any(line.startswith("FAIL  backend: the buckets are the counts in pytest's own summary line")
               for line in failed)
    assert any(line.startswith("FAIL  backend: the published console tail holds the same summary") for line in failed)


def test_a_passing_full_run_publishes_as_pass_and_verifies(tmp_path):
    public, out = publish_synthetic(tmp_path, passing=te.ALL_SUITES)
    assert public["verdict"] == "PASS" and [s["verdict"] for s in public["suites"]] == ["PASS"] * len(te.ALL_SUITES)
    lines = []
    assert te.verify_dir(out, emit=lines.append) is True, failed_lines(lines)


def test_an_interrupted_run_publishes_and_verifies(tmp_path):
    public, out = publish_synthetic(tmp_path, not_run=("mocked-mobile-360", "live", "live-isolated"))
    assert public["verdict"] == "NOT EVIDENCE"
    assert [s["verdict"] for s in public["suites"]][-3:] == ["NOT RUN", "NOT RUN", "NOT RUN"]
    lines = []
    assert te.verify_dir(out, emit=lines.append) is True, failed_lines(lines)

    def never_stopped(summary):
        summary["interrupted"] = False

    ok, lines = tamper(out, never_stopped)
    assert ok is False
    assert ("FAIL  a suite that was interrupted or never started means the run was interrupted "
            "(mocked-mobile-360, live, live-isolated)") in lines


def test_verify_rejects_a_suite_listed_twice_or_under_the_wrong_kind(tmp_path):
    _, out = publish_synthetic(tmp_path / "relabelled")

    def relabel(summary):
        summary["suites"][1]["kind"] = "pytest"

    ok, lines = tamper(out, relabel)
    assert ok is False
    assert "FAIL  mocked-desktop: kind pytest is the kind of that suite" in lines

    _, out = publish_synthetic(tmp_path / "twice")

    def twice(summary):
        summary["suites"].append(json.loads(json.dumps(summary["suites"][0])))

    ok, lines = tamper(out, twice)
    assert ok is False
    assert any(line.startswith("FAIL  the suites are known, listed once each, in the order they run") for line in lines)


def test_another_runner_version_is_noted_not_failed(tmp_path):
    # verify makes every check with its own code. A run made by another version of the runner is
    # still checked, and the reviewer is told which version to use if a check then disagrees.
    public, out = publish_synthetic(tmp_path)
    assert public["runner"] == {"path": "scripts/test_evidence.py", "sha256": te.sha256_file(SCRIPT)}

    def older_runner(summary):
        summary["runner"]["sha256"] = "0" * 64

    ok, lines = tamper(out, older_runner)
    assert ok is True, failed_lines(lines)
    assert any(line.startswith("note  this is not the runner that made the run") for line in lines)


def test_a_long_playwright_summary_is_published_whole():
    # With many failures the list reporter names each one under "N failed", and the last 40 lines
    # would start in the middle of the summary.
    failed = "".join(f"    [live] › live/a.spec.ts:{i}:3 › t{i} ───\n" for i in range(50))
    console = "Running 52 tests using 1 worker\n" + "  ✘ x\n" * 100 + "\n  50 failed\n" + failed + "  2 passed (9s)\n"
    tail = te.console_tail(console, "playwright", te.PLAYWRIGHT_TAIL_LINES)
    assert tail.splitlines()[0] == "  50 failed"
    assert te.parse_playwright_console(tail)["buckets"] == te.parse_playwright_console(console)["buckets"]
    short = "Running 1 test using 1 worker\n\n  1 passed (1s)\n"
    assert te.console_tail(short, "playwright", te.PLAYWRIGHT_TAIL_LINES) == short


def test_a_pytest_summary_followed_by_shutdown_noise_is_published():
    console = "." * 10 + "\n1 failed, 9 passed in 1.00s\n" + "Exception ignored in: <x>\n" * 100
    tail = te.console_tail(console, "pytest", te.BACKEND_TAIL_LINES)
    assert te.parse_pytest_console(tail)["line"] == "1 failed, 9 passed in 1.00s"
    assert len(tail.splitlines()) == 101


def test_a_deny_listed_value_stops_the_publish_and_writes_nothing(tmp_path, capsys):
    junit = PYTEST_JUNIT.replace("needs the archive", "needs the archive, key was sk-live-abcdef123456")
    with pytest.raises(te.PublishAbort) as caught:
        publish_synthetic(tmp_path, deny={"GAMEFORECAST_API_KEY (backend/.env)": "sk-live-abcdef123456"}, junit=junit)
    assert "the value of GAMEFORECAST_API_KEY (backend/.env)" in str(caught.value)
    assert "sk-live-abcdef123456" not in str(caught.value) + capsys.readouterr().out
    assert not (tmp_path / "docs").exists()


def test_a_foreign_email_stops_the_publish(tmp_path):
    junit = PYTEST_JUNIT.replace("needs the archive", "mail sent to someone@gmail.com")
    with pytest.raises(te.ScrubAbort):
        publish_synthetic(tmp_path, junit=junit)
    assert not (tmp_path / "docs").exists()


def test_summary_md_renders_the_same_after_a_json_round_trip(tmp_path):
    public, _ = publish_synthetic(tmp_path)
    assert te.render_summary_md(json.loads(json.dumps(public))) == te.render_summary_md(public)
    md = te.render_summary_md(public)
    assert md.startswith("# Test evidence 2026-10-07T0200Z-201442e\n\n**FAIL**")
    assert "- backend: exit 1, FAIL" in md and "- mocked-desktop: exit 1, FAIL" in md
    assert "python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-07T0200Z-201442e" in md


# ----------------------------------------------------------------------------- the concurrency guard
class Fake:
    """A detached sleeping process whose command line reads `command_line` (bash's exec -a).

    It is started in the background of a shell that exits at once, so it is re-parented and is not
    a descendant of this test process. The guard ignores its own process tree, so a child of the
    test would be ignored whatever its command line said.
    """

    def __init__(self, command_line: str):
        out = subprocess.run(["/bin/bash", "-c", f'(exec -a "{command_line}" sleep 30) >/dev/null 2>&1 & echo $!'],
                             capture_output=True, text=True, check=True).stdout
        self.pid = int(out.strip())
        deadline = time.time() + 5
        while time.time() < deadline:
            parent, command = te.process_table().get(self.pid, (0, ""))
            if command_line in command and parent != os.getpid():
                return
            time.sleep(0.05)
        self.kill()
        pytest.fail("the fake process never showed its command line")

    def kill(self):
        try:
            os.kill(self.pid, 9)
        except ProcessLookupError:
            pass


def start_fake(command_line: str) -> Fake:
    return Fake(command_line)


needs_pgrep = pytest.mark.skipif(not (shutil.which("pgrep") and shutil.which("ps") and os.path.exists("/bin/bash")),
                                 reason="needs pgrep, ps and bash")


@needs_pgrep
def test_guard_sees_a_playwright_test_runner():
    proc = start_fake("node /x/node_modules/.bin/playwright test --project=live")
    try:
        found = {r["pid"]: r for r in te.find_foreign_runners()}
        assert proc.pid in found
        assert found[proc.pid]["check"] == "playwright runner"
        assert found[proc.pid]["matched"] == "/.bin/playwright test"
        assert any(f"pid {proc.pid} " in reason for reason in te.guard_refusals(list(found.values())))
    finally:
        proc.kill()


@needs_pgrep
def test_guard_ignores_playwright_mcp_servers():
    proc = start_fake("node /x/node_modules/@playwright/mcp/cli.js --headless --isolated")
    try:
        found = te.find_foreign_runners()
        assert proc.pid not in {r["pid"] for r in found}
        mcp = {pid for pid, (_, command) in te.process_table().items() if "@playwright/mcp" in command}
        assert not mcp & {r["pid"] for r in found}
    finally:
        proc.kill()


@needs_pgrep
def test_guard_does_not_count_its_own_process_tree():
    # This test process is itself "python -m pytest": the guard must not refuse because of it.
    assert os.getpid() not in {r["pid"] for r in te.find_foreign_runners()}


def options(**overrides):
    values = dict(suites="mocked-desktop", allow_dirty=False, base_url=None, api_url=None, grep=None,
                  test_database_url=None, dry_run=False, no_publish=False, raw_root=None)
    values.update(overrides)
    return te.Options(argparse.Namespace(**values))


@needs_pgrep
def test_run_refuses_while_a_test_runner_is_active(monkeypatch):
    head = "201442e" + "0" * 33
    monkeypatch.setattr(te, "repo_state", lambda checkout=te.REPO: {"head": head, "dirty": False, "dirty_paths": []})
    monkeypatch.setattr(te, "origin_main", lambda checkout=te.REPO: {})
    checkout = {"toplevel": str(te.REPO), "head": head, "dirty_paths": []}
    monkeypatch.setattr(te, "listener", lambda port: {"port": port, "listening": True, "pids": [1], "pid": 1,
                                                      "checkout": checkout})
    monkeypatch.setattr(te, "tool_versions", lambda: {})
    monkeypatch.setattr(te, "run_child", lambda *a, **k: pytest.fail("a suite was started"))
    proc = start_fake("node /x/node_modules/.bin/playwright test")
    try:
        _, refusals, _ = te.preflight(options())
        assert any(reason.startswith(f"another test run is active: pid {proc.pid} ") for reason in refusals)
        assert te.cmd_run(options()) == 3
    finally:
        proc.kill()


# ----------------------------------------------------------------------------- the lock
def test_lock_is_exclusive_and_released(tmp_path):
    first, second = te.RunLock(tmp_path / "lock"), te.RunLock(tmp_path / "lock")
    first.acquire("run-1")
    with pytest.raises(te.Refused):
        second.acquire("run-2")
    first.release()
    assert not (tmp_path / "lock").exists()
    second.acquire("run-2")
    second.release()


def test_a_lock_whose_owner_is_gone_is_cleared_and_recorded(tmp_path):
    dead = subprocess.Popen(["true"])
    dead.wait()
    (tmp_path / "lock").mkdir()
    (tmp_path / "lock" / "owner.json").write_text(json.dumps({"pid": dead.pid, "run_id": "old", "acquired_at": "x"}))
    lock = te.RunLock(tmp_path / "lock")
    lock.acquire("new")
    assert lock.cleared_stale == {"pid": dead.pid, "run_id": "old", "acquired_at": "x"}
    assert json.loads((tmp_path / "lock" / "owner.json").read_text())["pid"] == os.getpid()
    lock.release()


# ----------------------------------------------------------------------------- preflight pieces
def test_lstart_is_read_as_local_time_and_returned_in_utc(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert te.iso(te.parse_lstart("Tue Oct  6 21:02:46 2026    ")) == "2026-10-07T01:02:46Z"
        assert te.parse_lstart("") is None and te.parse_lstart("garbage") is None
    finally:
        monkeypatch.undo()
        time.tzset()


def test_a_process_is_newer_than_the_code_only_from_the_next_second():
    changed = datetime(2026, 10, 5, 23, 0, 19, 500000, tzinfo=timezone.utc)
    assert te.started_after("2026-10-07T01:02:40Z", changed) is True
    assert te.started_after("2026-10-05T23:00:19Z", changed) is False   # same second: cannot tell
    assert te.started_after("2026-10-05T22:59:00Z", changed) is False
    assert te.started_after(None, changed) is None


def test_a_backend_started_before_its_code_changed_is_refused_for_live():
    server = {"url": "http://127.0.0.1:8000", "listening": True, "pid": 7, "started_at": "2026-10-05T22:00:00Z",
              "newest_source_change": "2026-10-05T23:00:19Z", "process_newer_than_code": False,
              "health": {"http_status": 200}, "checkout": {"toplevel": str(te.REPO), "head": "abc", "dirty_paths": []}}
    reasons = te.server_refusals("backend", server, {"head": "abc"}, False)
    assert len(reasons) == 1 and "did not start after the newest change" in reasons[0]
    server.update(process_newer_than_code=True)
    assert te.server_refusals("backend", server, {"head": "abc"}, False) == []
    assert "serves" in te.server_refusals("backend", server, {"head": "def"}, False)[0]


def app_tree(root: Path, files: dict) -> Path:
    """<root>/backend/app holding `files`: the checkout a backend serves."""
    app = root / "backend" / "app"
    for relative, content in files.items():
        (app / relative).parent.mkdir(parents=True, exist_ok=True)
        (app / relative).write_bytes(content)
    return app


def source_identity(tree, commit=HEAD, dirty=()):
    """GET /health's `source`, as backend/app/core/source_identity.py records it at start-up."""
    return {"commit": commit, "commit_dirty_app_files": list(dirty), "app_tree_sha256": tree, "app_files": 1,
            "started_at": "2026-10-07T22:53:40Z"}


def test_the_app_tree_digest_is_the_documented_algorithm(tmp_path):
    """backend/app/core/source_identity.py's algorithm as one byte string: path, NUL, bytes, NUL,
    in POSIX path order, over *.py outside __pycache__ and nothing else."""
    app = app_tree(tmp_path, {"main.py": b"app = 1\n", "services/slips.py": b"",
                              "__pycache__/main.cpython-311.pyc": b"\x00", "services/__pycache__/stale.py": b"x",
                              "notes.txt": b"not source"})
    expected = hashlib.sha256(b"main.py\0app = 1\n\0services/slips.py\0\0").hexdigest()
    assert te.app_tree_digest(app) == (expected, 2)
    assert te.app_tree_digest(tmp_path / "missing") == (None, 0)


def test_health_snapshot_keeps_the_source_identity_as_scalars(monkeypatch):
    body = {"status": "healthy", "environment": "development", "version": "0.1.0",
            "started_at": "2026-10-07T22:53:40Z", "database": "soccer_predictions",
            "source": dict(source_identity("a" * 64, dirty=["backend/app/x.py"]), unexpected={"nested": True})}
    monkeypatch.setattr(te, "http_get_json", lambda url, timeout=5.0: (200, body))
    record = te.health_snapshot("http://127.0.0.1:8000")
    assert record["http_status"] == 200 and record["database"] == "soccer_predictions"
    assert record["source"] == {"commit": HEAD, "app_tree_sha256": "a" * 64, "app_files": 1,
                                "started_at": "2026-10-07T22:53:40Z", "commit_dirty_app_files": ["backend/app/x.py"]}
    monkeypatch.setattr(te, "http_get_json", lambda url, timeout=5.0: (200, {"status": "healthy", "version": "0.1.0"}))
    older = te.health_snapshot("http://127.0.0.1:8000")
    assert "source" not in older and "started_at" not in older and older["status"] == "healthy"


def test_running_code_is_measured_from_the_backends_own_account(tmp_path):
    app = app_tree(tmp_path, {"main.py": b"app = 1\n"})
    tree, _ = te.app_tree_digest(app)
    health = {"http_status": 200, "source": source_identity(tree)}
    record = te.running_code_record(health, HEAD, app)
    assert record["basis"] == "measured" and record["tree_matches"] is True and record["commit_matches"] is True
    assert (record["commit_served"], record["commit_head"], record["tree_served"]) == (HEAD, HEAD, tree)
    (app / "main.py").write_bytes(b"app = 2\n")
    changed = te.running_code_record(health, "f" * 40, app)
    assert changed["tree_matches"] is False and changed["commit_matches"] is False and changed["tree_now"] != tree
    assert te.running_code_record({"http_status": 200, "status": "healthy"}, HEAD, app) is None


def test_a_backend_without_a_source_identity_is_inferred_from_timestamps_and_labelled(tmp_path):
    app = app_tree(tmp_path, {"main.py": b"app = 1\n"})
    changed = datetime(2026, 10, 7, 22, 0, 0, tzinfo=timezone.utc).timestamp()
    os.utime(app / "main.py", (changed, changed))
    server = {"cwd": str(tmp_path / "backend"), "started_at": "2026-10-07T22:53:40Z",
              "health": {"http_status": 200, "status": "healthy"},
              "checkout": {"toplevel": str(tmp_path), "head": HEAD, "dirty_paths": []}}
    assert te.running_code_of(server) == {"basis": "inferred", "newest_source_change": "2026-10-07T22:00:00Z",
                                          "process_newer_than_code": True}
    server["health"]["source"] = source_identity(te.app_tree_digest(app)[0])
    assert te.running_code_of(server)["basis"] == "measured"


def test_a_backend_whose_loaded_tree_is_not_the_checkouts_is_refused_for_live():
    """The measured rule replaces the timestamp rule: a digest that differs refuses, a digest that
    matches is not second-guessed by a timestamp, and a commit that moved on without touching the
    application tree is recorded, not refused."""
    measured = {"basis": "measured", "tree_served": "a" * 64, "tree_now": "b" * 64, "tree_matches": False,
                "commit_served": "abc", "commit_head": "abc", "commit_matches": True}
    server = {"url": "http://127.0.0.1:8000", "listening": True, "pid": 7, "started_at": "2026-10-07T22:53:40Z",
              "health": {"http_status": 200}, "running_code": measured,
              "checkout": {"toplevel": str(te.REPO), "head": "abc", "dirty_paths": []}}
    reasons = te.server_refusals("backend", server, {"head": "abc"}, False)
    assert len(reasons) == 1 and "is not running the application tree on disk" in reasons[0]
    assert "aaaaaaaaaaaa" in reasons[0] and "bbbbbbbbbbbb" in reasons[0]
    measured.update(tree_now="a" * 64, tree_matches=True)
    server["process_newer_than_code"] = False
    assert te.server_refusals("backend", server, {"head": "abc"}, False) == []
    measured.update(commit_served="old", commit_matches=False)
    assert te.server_refusals("backend", server, {"head": "abc"}, False) == []
    measured.update(tree_now=None, tree_matches=False)
    assert "nothing readable" in te.server_refusals("backend", server, {"head": "abc"}, False)[0]


def test_the_inferred_rule_still_refuses_a_backend_labelled_inferred():
    server = {"url": "http://127.0.0.1:8000", "listening": True, "pid": 7, "started_at": "2026-10-05T22:00:00Z",
              "health": {"http_status": 200},
              "running_code": {"basis": "inferred", "newest_source_change": "2026-10-05T23:00:19Z",
                               "process_newer_than_code": False},
              "checkout": {"toplevel": str(te.REPO), "head": "abc", "dirty_paths": []}}
    reasons = te.server_refusals("backend", server, {"head": "abc"}, False)
    assert len(reasons) == 1 and "did not start after the newest change" in reasons[0]
    assert "2026-10-05T23:00:19Z" in reasons[0]
    assert te.running_code_brief(server) == "inferred, process newer than code: False"


def test_summary_md_shows_the_running_code_and_renders_older_records_unchanged():
    base = {"url": "http://127.0.0.1:8000", "listening": True, "pid": 7, "started_at": "2026-10-07T22:53:40Z",
            "command": "uvicorn app.main:app", "cwd": "<repo>/backend",
            "checkout": {"toplevel": "<repo>", "head": HEAD, "dirty_paths": []},
            "health": {"http_status": 200, "status": "healthy", "database": "soccer_predictions",
                       "source": {"commit": HEAD, "app_tree_sha256": "a" * 64}},
            "unchanged_at_end": True}

    def lines(server):
        return te._render_environment({"repository": {}, "servers": {"backend": server}}, [])

    measured = dict(base, running_code={"basis": "measured", "tree_served": "a" * 64, "tree_now": "a" * 64,
                                        "tree_matches": True, "commit_served": HEAD, "commit_head": HEAD,
                                        "commit_matches": True, "dirty_app_files_at_start": []})
    rendered = lines(measured)
    (line,) = [l for l in rendered if l.startswith("- Running code")]
    assert "measured" in line and f"`{'a' * 64}`" in line and "match" in line and "DIFFERENT" not in line
    assert f"`{HEAD}`" in line and "when it started: 0" in line
    (health_line,) = [l for l in rendered if l.startswith("- /health")]
    assert "source" not in health_line and "soccer_predictions" in health_line

    differing = dict(measured, running_code=dict(measured["running_code"], tree_now="b" * 64, tree_matches=False,
                                                 dirty_app_files_at_start=None))
    (line,) = [l for l in lines(differing) if l.startswith("- Running code")]
    assert "DIFFERENT" in line and "when it started: unknown" in line

    inferred = dict(base, running_code={"basis": "inferred", "newest_source_change": "2026-10-07T02:48:04Z",
                                        "process_newer_than_code": True})
    (line,) = [l for l in lines(inferred) if l.startswith("- Running code")]
    assert "inferred from modification times" in line and "2026-10-07T02:48:04Z" in line and "yes" in line

    # A record made before the backend published a source identity, as the published folders hold it.
    older = dict(base, newest_source_change="2026-10-07T02:48:04Z", process_newer_than_code=True,
                 health={"http_status": 200, "status": "healthy", "environment": "development", "version": "0.1.0"})
    rendered = lines(older)
    assert "- Newest app/**/*.py change 2026-10-07T02:48:04Z; process newer than the code: yes" in rendered
    assert not [l for l in rendered if l.startswith("- Running code")]
    assert ("- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0'}"
            in rendered)


def test_provider_snapshot_keeps_kinds_not_text():
    status = {"checked_at": "2026-10-07T01:10:52Z", "chain": [
        {"name": "livescore", "integration_status": "live", "configured": True, "last_success_at": None,
         "last_error_at": "2026-10-07T01:00:00Z", "cooling_down": "until 02:00 after HTTP 401",
         "last_error": "authentication rejected (HTTP 401) for https://x/list.json?key=abc123&secret=def456",
         "budget": {"used_today": 3}},
        {"name": "thesportsdb", "integration_status": "fallback", "last_error": "timed out after 10s"}],
        "forecasts": {"active_provider": "gameforecast", "integration_status": "live", "configured": True,
                      "last_sync": {"synced_at": "2026-10-07T00:01:00Z", "competitions": {"x": {}}}},
        "scheduler": {"tasks": {"fixtures": {"last_error": "every match-data source refused (HTTP 401)",
                                             "last_error_at": "2026-10-07T00:00:00Z", "last_result": {"a": 1}}}}}
    snapshot = te.provider_snapshot(status)
    assert [p["error_kind"] for p in snapshot["providers"]] == ["http_401", "timeout", None]
    assert snapshot["providers"][0]["cooling_down"] is True
    assert snapshot["scheduler_tasks"] == {
        "fixtures": {"last_success_at": None, "last_error_at": "2026-10-07T00:00:00Z", "error_kind": "http_401"}}
    dumped = json.dumps(snapshot)
    for leaked in ("abc123", "def456", "key=", "budget", "used_today", "competitions", "last_result", "until 02:00"):
        assert leaked not in dumped


def test_conftest_default_is_read_in_both_forms(tmp_path):
    reads = tmp_path / "reads.py"
    reads.write_text('import os\nTEST_DATABASE_URL = os.environ.get(\n'
                     '    "TEST_DATABASE_URL", "postgresql://u:p@h:5432/x_test")\n')
    fixed = tmp_path / "fixed.py"
    fixed.write_text('TEST_DATABASE_URL = "postgresql://u:p@h:5432/x_test"\n')
    assert te.conftest_database_default(reads) == ("postgresql://u:p@h:5432/x_test", True)
    assert te.conftest_database_default(fixed) == ("postgresql://u:p@h:5432/x_test", False)
    assert te.conftest_database_default(tmp_path / "missing.py") == (None, False)


def test_database_refusals():
    default = "postgresql://u:p@localhost:5432/soccer_predictions_test"
    own = "postgresql://u:p@localhost:5432/soccer_predictions_test_evidence"
    assert te.database_refusals(own, default, True) == []
    assert "does not say it is a test database" in te.database_refusals(
        "postgresql://u:p@localhost:5432/soccer_predictions", default, True)[0]
    assert "ignores TEST_DATABASE_URL" in te.database_refusals(own, default, False)[0]
    assert te.database_refusals(None, None, False) == ["no backend test database: set TEST_DATABASE_URL"]
    assert te.describe_database_url(own) == {"scheme": "postgresql", "host": "localhost", "port": 5432,
                                             "database": "soccer_predictions_test_evidence"}


def test_porcelain_with_a_rename_and_evidence_output():
    report = "?? docs/evidence/test-reports/run/summary.md"
    raw = b" M backend/tests/conftest.py\0R  new.py\0old.py\0" + report.encode() + b"\0?? notes.txt\0"
    entries = te.parse_porcelain(raw)
    assert entries == [" M backend/tests/conftest.py", "R  new.py", report, "?? notes.txt"]
    kept = [e for e in entries if not te.is_evidence_output(e)]
    assert kept == [" M backend/tests/conftest.py", "R  new.py", "?? notes.txt"]


def test_run_id():
    now = datetime(2026, 10, 7, 2, 5, 33, tzinfo=timezone.utc)
    assert te.make_run_id(now, "201442e" + "0" * 33, False, False) == "2026-10-07T0205Z-201442e"
    assert te.make_run_id(now, "201442e" + "0" * 33, True, True) == "2026-10-07T0205Z-201442e-dirty-partial"


def test_a_subset_of_suites_is_partial_and_runs_in_the_canonical_order():
    opts = options(suites="live,backend")
    assert opts.suites == ["backend", "live"]
    assert opts.partial_reasons == ["only backend, live requested"]
    assert options(suites=",".join(te.ALL_SUITES)).partial_reasons == []
    assert options(suites=",".join(te.ALL_SUITES), grep="parlay").partial_reasons == ["tests filtered with --grep"]


def test_the_isolated_suite_belongs_to_a_complete_run():
    """live-isolated drives the isolated pair; a run without it is partial, as any dropped suite is."""
    assert te.ALL_SUITES[-1] == "live-isolated" and "live-isolated" not in te.MAIN_PAIR_PROJECTS
    assert te.partial_reasons_for(list(te.LEGACY_SUITES), False) == [
        "only backend, mocked-desktop, mocked-mobile, mocked-mobile-360, live requested"]
    # Against the set a runner had before the suite existed, the same five are complete.
    assert te.partial_reasons_for(list(te.LEGACY_SUITES), False, te.LEGACY_SUITES) == []
    opts = options(suites=",".join(te.ALL_SUITES), isolated_base_url=None, isolated_api_url=None)
    assert opts.partial_reasons == [] and opts.isolated_api_url == te.DEFAULT_ISOLATED_API_URL
    env = te.playwright_env("live-isolated", Path("/r"), "http://localhost:3100", "http://127.0.0.1:8000",
                            "http://localhost:3101", "http://127.0.0.1:8001")
    assert env["E2E_ISOLATED_API_URL"] == "http://127.0.0.1:8001" and env["E2E_API_URL"] == "http://127.0.0.1:8000"
    assert "E2E_ISOLATED_API_URL" not in te.playwright_env("live", Path("/r"), "http://localhost:3100", "http://127.0.0.1:8000")


def test_a_published_run_is_judged_complete_against_the_suite_set_its_runner_had():
    """A summary from before suites_available existed ran the legacy five; a later one must record
    its set, so leaving the field out cannot pass a dropped suite off as a complete run."""
    assert te.available_suites({"started_at": "2026-10-07T03:01:09Z"}) == list(te.LEGACY_SUITES)
    assert te.available_suites({"started_at": "2026-10-08T05:00:00Z",
                                "suites_available": ["backend", "live"]}) == ["backend", "live"]
    assert te.available_suites({"started_at": "2026-10-08T05:00:00Z"}) is None
    assert te.available_suites({}) is None


def test_live_isolated_is_refused_unless_its_backend_is_really_isolated():
    def servers(database, main="soccer_predictions", listening=True):
        health = {"database": database} if database is not None else {}
        return {"backend": {"listening": True, "health": {"database": main}},
                "backend-isolated": {"listening": listening, "health": health}}

    opts = options(suites="live-isolated")
    assert te.isolation_refusals(servers("soccer_predictions_e2e"), opts) == []
    assert any("live database" in r for r in te.isolation_refusals(servers("soccer_predictions"), opts))
    assert any("same database" in r for r in te.isolation_refusals(servers("copy", main="copy"), opts))
    assert any("does not say" in r for r in te.isolation_refusals(servers(None), opts))
    # Not listening is the listener's own refusal; nothing is claimed about its database.
    assert te.isolation_refusals(servers(None, listening=False), opts) == []
    same = options(suites="live-isolated", isolated_api_url="http://localhost:8000")
    assert any("is the main backend" in r for r in te.isolation_refusals(servers("soccer_predictions_e2e"), same))


def test_suite_commands():
    raw = Path("/r")
    assert te.backend_command(raw)[3:] == [
        "-o", "addopts=", "-p", "no:cacheprovider", "-q", "-rfEs", "--junitxml=/r/backend.junit.xml",
        "-o", "junit_suite_name=backend", "-o", "junit_family=xunit2", "-o", "junit_logging=no"]
    assert te.playwright_command("mocked-mobile-360", raw)[1:] == [
        "test", "--project=mocked-mobile-360", "--forbid-only", "--retries=0",
        "--output=/r/artifacts-mocked-mobile-360", "--reporter=list,json,junit"]
    env = te.playwright_env("live", raw, "http://localhost:3100", "http://127.0.0.1:8000")
    assert env["PLAYWRIGHT_JSON_OUTPUT_FILE"] == "/r/playwright-live.json"
    assert env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"] == "/r/playwright-live.junit.xml"
    assert env["PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME"] == "1" and env["FORCE_COLOR"] == "0"


def test_inherited_reporter_settings_never_reach_a_suite(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_HTML_OUTPUT_DIR", "/elsewhere")
    monkeypatch.setenv("PW_TEST_REPORTER", "dot")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/browsers")
    env = te.child_env({"FORCE_COLOR": "0"})
    assert "PLAYWRIGHT_HTML_OUTPUT_DIR" not in env and "PW_TEST_REPORTER" not in env and "PYTEST_ADDOPTS" not in env
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "/browsers" and env["FORCE_COLOR"] == "0"


def test_run_child_returns_the_childs_own_exit_code(tmp_path):
    console = tmp_path / "c.log"
    ran = te.run_child([sys.executable, "-c", "print('  1 failed'); raise SystemExit(7)"], tmp_path, dict(os.environ),
                       console, echo=False)
    assert ran["exit_code"] == 7 and ran["interrupted"] is False
    assert console.read_text() == "  1 failed\n"

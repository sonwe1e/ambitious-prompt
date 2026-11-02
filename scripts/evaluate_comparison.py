#!/usr/bin/env python3
"""Validate annotated paired comparisons; never judge model output itself.

Python 3.9+, standard library only.  Usage::

    python3 evaluate_comparison.py annotations.json --protocol protocol.json
    python3 evaluate_comparison.py annotations.json --protocol protocol.json \
        --manifest frozen.json \
        --output decision.json

The CLI always prints one JSON object. Exit 0 means a complete evaluation (which
can reject the candidate), 1 means insufficient evidence, and 2 means malformed
input or an I/O error. A zero exit code is NOT a positive experimental result.
Read ``conclusion`` and ``gate.passed``. This program does not deploy anything.
All result JSON is ASCII-escaped, including error results, so a JSON-escaped
isolated Unicode surrogate cannot break stdout or --output encoding.

Schema v1 (all shown fields required except independent_reviewer, which may be
absent/null while review is pending; a completed evaluation requires it)::

    {
      "schema_version": 1,
      "versions": {"candidate": "v13", "baseline": "v12"},
      "protocol": {
        "case_counts": {"critical": 4, "control": 4, "fixed_context": 2},
        "main_repeats": [1, 2],
        "fixed_repeats": [1]
      },
      "cases": [
        {"id": "K1", "kind": "critical"},
        {"id": "K2", "kind": "critical"},
        {"id": "K3", "kind": "critical"},
        {"id": "K4", "kind": "critical"},
        {"id": "C1", "kind": "control"},
        {"id": "C2", "kind": "control"},
        {"id": "C3", "kind": "control"},
        {"id": "C4", "kind": "control"},
        {"id": "F1", "kind": "fixed_context"},
        {"id": "F2", "kind": "fixed_context"}
      ],
      "records": [
        {
          "case_id": "K1", "repeat": 1,
          "reviewer": {"id": "reviewer-a", "kind": "independent_model"},
          "independently_reviewed": true,
          "independent_reviewer": {"id": "reviewer-b", "kind": "human"},
          "source_refs": ["anonymous/K1/r1.txt#full-paired-transcripts"],
          "capture": {
            "verdict": "candidate", "evidence_refs": ["review/K1-r1#capture"]
          },
          "downstream": {
            "verdict": "candidate", "evidence_refs": ["review/K1-r1#downstream"]
          },
          "core_counterexample": {
            "verdict": "no", "evidence_refs": ["review/K1-r1#core-check"]
          },
          "fixed_adoption": {"verdict": "not_applicable", "evidence_refs": []},
          "candidate": {
            "information_requests": 1, "blocking_rounds": 1,
            "repeated_confirmations": 0, "severe_violations": []
          },
          "baseline": {
            "information_requests": 0, "blocking_rounds": 0,
            "repeated_confirmations": 0, "severe_violations": []
          }
        }
      ]
    }

The abbreviated records above need the other 17 rows for the stated protocol.
Case counts are explicitly declared positive integers; the current experiment
uses 4 critical, 4 control, 2 fixed-context tasks. Main repeats must be [1, 2].
Fixed repeats must be [1] or [1, 2]. Fixed-context rows are adoption diagnostics
and NEVER count toward stable main-experiment gains, including burden gains.

Critical capture/downstream use candidate/baseline/tie/insufficient and cannot
be not_applicable. Control downstream may additionally be not_applicable;
control capture still requires a real judgment. Fixed-context capture and
downstream may be not_applicable. Main rows require fixed_adoption=
not_applicable; fixed-context rows require a real fixed_adoption judgment.
Nonapplicable judgments may have empty evidence_refs, are reported separately,
are excluded from applicable-judgment denominators, and never count as wins.
core_counterexample uses yes/no/insufficient:
it is an explicitly reviewed *reliable reverse core case*, such as the baseline
retaining a critical requirement the candidate omitted. The evaluator does not
infer reliability from output words or from another verdict. A violation is::

    {"kind": "goal", "description": "Concrete violated requirement and act",
     "evidence_refs": ["anonymous/K1/r1.txt#quote-or-location"]}

Violation kinds: goal, authorization, hard_constraint. Counts are annotated
independent information requests, blocking clarification rounds, and repeated
confirmations, not counts of question marks or sentences. Every judgment needs
nonempty evidence_refs, except not_applicable. source_refs identify the paired
source material; references may contain paths, locations, and quoted excerpts.
Empty severe_violations means the reviewers found none, not that review was
skipped. All unresolved disputes must use insufficient. Unknown enum values,
booleans used as integers, duplicate JSON keys, duplicate cases/rows, undeclared
cases/repeats, wrong types, missing fields, and extra fields are rejected.

Two reviewers must actually be independent. The tool can only require the flag
and distinct reviewer IDs. Reference strings, reviewer IDs, empty violation
lists, and repeat numbers are declarations, NOT proof of semantic validity,
authentic source evidence, independent execution, or independent review.

Predeclared engineering gate, NOT a statistical significance claim:
  * an explicitly supplied external protocol matches the annotation protocol;
  * complete, independently reviewed matrix, with no insufficient judgments;
  * at least TWO distinct critical tasks have candidate capture AND candidate
    actual downstream wins in BOTH independent repeats;
  * no explicitly reliable core counterexample;
  * no control row adds blocking rounds or repeated confirmations;
  * no fixed-context adoption row favors baseline;
  * no candidate severe goal/authorization/hard-constraint violations;
  * if a frozen manifest was supplied, every listed file hash matches.

External protocol: --protocol reads a JSON object with case_counts,
main_repeats, and fixed_repeats at the top level, using the same types and
allowed values as the annotation protocol. Extra explanatory fields are kept
in protocol_binding.document; they are not silently dropped or interpreted as
additional executable rules. All three required fields must match exactly.
The input's own protocol declaration cannot replace this external binding.
Without --protocol, the tool still reports structurally valid annotations and
counts, but protocol_binding.status is unbound, conclusion is insufficient,
and gate.passed is false. A missing, damaged, or mismatched external protocol
also prevents passage. These checks bind the matrix dimensions, not case IDs.

Baseline violations are reported, but do not automatically block candidate
gains. No weighted score, significance test, keyword inference, or text judge
is used. Outcomes distinguish limited_end_to_end_gain, local_end_to_end_gain_
below_threshold, capture_only_gain, downstream_only_gain, burden_only_gain,
parity, unstable_or_mixed, regression_or_constraint_failure, and insufficient.
Less burden means Pareto improvement in the three separately reported counts:
no count increases in either repeat, with a reduction in each repeat. The
burden_only category additionally requires all applicable main capture/
downstream judgments to be ties and no main-row burden increase. Fixed-path
improvements do not prove that asking questions was effective.

Optional frozen manifest (relative paths resolve against its own directory)::

    {"schema_version": 1, "files": [
      {"path": "protocol.json", "sha256": "<64 lowercase hex digits>"},
      {"path": "baseline/SKILL.md", "sha256": "<64 lowercase hex digits>"},
      {"path": "candidate/SKILL.md", "sha256": "<64 lowercase hex digits>"}
    ]}

When --manifest is supplied, it must cover the exact --protocol file and the
same bytes read for protocol binding. Hashing another protocol file is not a
substitute. The protocol and manifest should be frozen separately before runs.
The tool cannot prove when they were frozen, authenticate the manifest, or
prove that listed runtime files were loaded by the model. Unlisted files are
outside the manifest's coverage.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


SCHEMA_VERSION = 1
TOOL_VERSION = "1.2"
KINDS = ("critical", "control", "fixed_context")
VERSIONS = ("candidate", "baseline")
METRICS = ("information_requests", "blocking_rounds", "repeated_confirmations")
VERDICTS = ("candidate", "baseline", "tie", "insufficient")
REVIEW_KINDS = ("human", "independent_model")
VIOLATION_KINDS = ("goal", "authorization", "hard_constraint")
MIN_STABLE_CRITICAL_CASES = 2
PROTOCOL_FIELDS = ("case_counts", "main_repeats", "fixed_repeats")


def comparison_verdicts(kind, field):
    if kind == "fixed_context" or (kind == "control" and field == "downstream"):
        return VERDICTS + ("not_applicable",)
    return VERDICTS


class DuplicateKeyError(ValueError):
    """JSON object key was declared more than once."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON object key: {!r}".format(key))
        result[key] = value
    return result


def parse_json(contents):
    def reject_constant(value):
        raise ValueError("non-JSON numeric constant: " + value)

    return json.loads(
        contents,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


def read_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def issue(code, location, message):
    return {"code": code, "location": location, "message": message}


class Validator:
    def __init__(self):
        self.errors = []

    def error(self, code, where, message):
        self.errors.append(issue(code, where, message))

    def obj(self, value, where, required, optional=()):
        if not isinstance(value, dict):
            self.error("wrong_type", where, "expected an object")
            return False
        for key in sorted(set(required) - set(value)):
            self.error("missing_field", where + "." + key, "required field is absent")
        for key in sorted(set(value) - set(required) - set(optional)):
            self.error("unknown_field", where + "." + key, "field is not in schema v1")
        return True

    def string(self, value, where):
        if not isinstance(value, str) or not value.strip():
            self.error("wrong_type", where, "expected a nonempty string")
            return False
        return True

    def integer(self, value, where, minimum=0):
        if type(value) is not int or value < minimum:
            self.error("wrong_type", where, "expected an integer >= {} (not bool)".format(minimum))
            return False
        return True

    def boolean(self, value, where):
        if type(value) is not bool:
            self.error("wrong_type", where, "expected a boolean")
            return False
        return True

    def enum(self, value, where, allowed):
        if not isinstance(value, str) or value not in allowed:
            self.error("unknown_verdict_or_enum", where, "expected one of " + ", ".join(allowed))
            return False
        return True

    def array(self, value, where):
        if not isinstance(value, list):
            self.error("wrong_type", where, "expected an array")
            return False
        return True

    def refs(self, value, where, allow_empty=False):
        if not self.array(value, where):
            return
        if not value and not allow_empty:
            self.error("missing_evidence", where, "at least one evidence reference is required")
        seen = set()
        for index, ref in enumerate(value):
            if self.string(ref, "{}[{}]".format(where, index)):
                if ref in seen:
                    self.error("duplicate_reference", where, "duplicate reference: " + ref)
                seen.add(ref)

    def reviewer(self, value, where):
        if self.obj(value, where, ("id", "kind")):
            self.string(value.get("id"), where + ".id")
            self.enum(value.get("kind"), where + ".kind", REVIEW_KINDS)

    def judgment(self, value, where, allowed):
        if self.obj(value, where, ("verdict", "evidence_refs")):
            verdict = value.get("verdict")
            self.enum(verdict, where + ".verdict", allowed)
            self.refs(value.get("evidence_refs"), where + ".evidence_refs", verdict == "not_applicable")


def validate_protocol_fields(protocol, v, where, allow_explanations=False):
    expected_counts = None
    expected_repeats = {}
    optional = tuple(protocol) if allow_explanations and isinstance(protocol, dict) else ()
    if v.obj(protocol, where, PROTOCOL_FIELDS, optional):
        counts = protocol.get("case_counts")
        if v.obj(counts, where + ".case_counts", KINDS):
            count_ok = [v.integer(counts.get(kind), where + ".case_counts." + kind, 1) for kind in KINDS]
            if all(count_ok):
                expected_counts = counts
        for field, allowed in (("main_repeats", ([1, 2],)), ("fixed_repeats", ([1], [1, 2]))):
            repeats = protocol.get(field)
            if v.array(repeats, where + "." + field):
                for index, repeat in enumerate(repeats):
                    v.integer(repeat, "{}.{}[{}]".format(where, field, index), 1)
                if any(type(repeat) is not int for repeat in repeats) or repeats not in allowed:
                    v.error("repeat_protocol", where + "." + field, "expected " + " or ".join(map(str, allowed)))
                else:
                    expected_repeats[field] = repeats
    return expected_counts, expected_repeats


def read_protocol(path):
    result = {
        "requested": path is not None,
        "status": "unbound" if path is None else "invalid",
        "path": None if path is None else str(path),
        "sha256": None,
        "document": None,
        "requirements": None,
        "requirements_match": None,
        "manifest_coverage": "not_checked",
        "mismatches": [],
        "errors": [],
    }
    if path is None:
        return result
    try:
        resolved = Path(path).resolve()
        contents = resolved.read_bytes()
        result["path"] = str(resolved)
        result["sha256"] = hashlib.sha256(contents).hexdigest()
        result["document"] = parse_json(contents.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        result["errors"].append(issue("protocol_read_error", str(path), str(exc)))
        return result
    v = Validator()
    validate_protocol_fields(result["document"], v, "external_protocol", allow_explanations=True)
    result["errors"] = v.errors
    if not v.errors:
        result["requirements"] = {field: result["document"][field] for field in PROTOCOL_FIELDS}
        result["status"] = "loaded"
    return result


def bind_protocol(external_protocol, declared_protocol, manifest):
    result = dict(external_protocol)
    if result["status"] == "loaded":
        result["mismatches"] = [
            {"field": field, "external": result["requirements"][field], "annotations": declared_protocol[field]}
            for field in PROTOCOL_FIELDS
            if result["requirements"][field] != declared_protocol[field]
        ]
        result["requirements_match"] = not result["mismatches"]
        result["status"] = "matched" if result["requirements_match"] else "mismatch"
    if not manifest["requested"]:
        result["manifest_coverage"] = "not_requested"
    elif manifest["status"] == "invalid":
        result["manifest_coverage"] = "invalid_manifest"
    elif not result["requested"] or result["sha256"] is None:
        result["manifest_coverage"] = "unbound"
    else:
        entries = [entry for entry in manifest["files"] if entry.get("resolved_path") == result["path"]]
        if not entries:
            result["manifest_coverage"] = "not_listed"
        elif any(entry["matches"] and entry["actual_sha256"] == result["sha256"] for entry in entries):
            result["manifest_coverage"] = "matched"
        else:
            result["manifest_coverage"] = "mismatch"
    return result


def validate(data):
    v = Validator()
    if not v.obj(data, "$", ("schema_version", "versions", "protocol", "cases", "records")):
        return v.errors
    if type(data.get("schema_version")) is not int or data.get("schema_version") != SCHEMA_VERSION:
        v.error("schema_version", "$.schema_version", "expected integer 1")

    versions = data.get("versions")
    if v.obj(versions, "$.versions", VERSIONS):
        for name in VERSIONS:
            v.string(versions.get(name), "$.versions." + name)
        if isinstance(versions.get("candidate"), str) and versions.get("candidate") == versions.get("baseline"):
            v.error("same_versions", "$.versions", "candidate and baseline labels must differ")

    expected_counts, expected_repeats = validate_protocol_fields(data.get("protocol"), v, "$.protocol")

    case_map = {}
    cases = data.get("cases")
    if v.array(cases, "$.cases"):
        observed_counts = Counter()
        for index, case in enumerate(cases):
            where = "$.cases[{}]".format(index)
            if not v.obj(case, where, ("id", "kind")):
                continue
            id_ok = v.string(case.get("id"), where + ".id")
            kind_ok = v.enum(case.get("kind"), where + ".kind", KINDS)
            if id_ok and case["id"] in case_map:
                v.error("duplicate_case", where + ".id", "case ID already declared")
            if id_ok and kind_ok:
                case_map[case["id"]] = case["kind"]
                observed_counts[case["kind"]] += 1
        if expected_counts is not None:
            for kind in KINDS:
                if observed_counts[kind] != expected_counts[kind]:
                    v.error("case_count_mismatch", "$.cases", "{}: declared {}, observed {}".format(kind, expected_counts[kind], observed_counts[kind]))

    records = data.get("records")
    if v.array(records, "$.records"):
        seen = set()
        required = (
            "case_id", "repeat", "reviewer", "independently_reviewed", "source_refs",
            "capture", "downstream", "core_counterexample", "fixed_adoption",
            "candidate", "baseline",
        )
        for index, record in enumerate(records):
            where = "$.records[{}]".format(index)
            if not v.obj(record, where, required, ("independent_reviewer",)):
                continue
            id_ok = v.string(record.get("case_id"), where + ".case_id")
            repeat_ok = v.integer(record.get("repeat"), where + ".repeat", 1)
            kind = case_map.get(record["case_id"]) if id_ok else None
            if id_ok and kind is None:
                v.error("undeclared_case", where + ".case_id", "case ID is not in cases")
            if id_ok and repeat_ok:
                key = (record["case_id"], record["repeat"])
                if key in seen:
                    v.error("duplicate_record", where, "duplicate (case_id, repeat): {}".format(key))
                seen.add(key)
                field = "fixed_repeats" if kind == "fixed_context" else "main_repeats"
                if kind and field in expected_repeats and record["repeat"] not in expected_repeats[field]:
                    v.error("undeclared_repeat", where + ".repeat", "repeat is not in the protocol for this case kind")
            v.reviewer(record.get("reviewer"), where + ".reviewer")
            v.boolean(record.get("independently_reviewed"), where + ".independently_reviewed")
            if record.get("independent_reviewer") is not None:
                v.reviewer(record["independent_reviewer"], where + ".independent_reviewer")
            v.refs(record.get("source_refs"), where + ".source_refs")
            for field in ("capture", "downstream"):
                v.judgment(record.get(field), where + "." + field, comparison_verdicts(kind, field))
            v.judgment(record.get("core_counterexample"), where + ".core_counterexample", ("yes", "no", "insufficient"))
            adoption_allowed = VERDICTS if kind == "fixed_context" else ("not_applicable",)
            v.judgment(record.get("fixed_adoption"), where + ".fixed_adoption", adoption_allowed)
            for name in VERSIONS:
                outcome = record.get(name)
                loc = where + "." + name
                if not v.obj(outcome, loc, METRICS + ("severe_violations",)):
                    continue
                for metric in METRICS:
                    v.integer(outcome.get(metric), loc + "." + metric)
                violations = outcome.get("severe_violations")
                if v.array(violations, loc + ".severe_violations"):
                    for n, violation in enumerate(violations):
                        violation_loc = "{}.severe_violations[{}]".format(loc, n)
                        if v.obj(violation, violation_loc, ("kind", "description", "evidence_refs")):
                            v.enum(violation.get("kind"), violation_loc + ".kind", VIOLATION_KINDS)
                            v.string(violation.get("description"), violation_loc + ".description")
                            v.refs(violation.get("evidence_refs"), violation_loc + ".evidence_refs")
    return v.errors


def check_manifest(path):
    if path is None:
        return {"requested": False, "status": "not_requested", "files": [], "errors": []}
    result = {"requested": True, "status": "invalid", "files": [], "errors": []}
    try:
        data = read_json(path)
    except (OSError, UnicodeError, ValueError) as exc:
        result["errors"].append(issue("manifest_read_error", str(path), str(exc)))
        return result
    v = Validator()
    if v.obj(data, "manifest", ("schema_version", "files")):
        if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
            v.error("schema_version", "manifest.schema_version", "expected integer 1")
        files = data.get("files")
        if v.array(files, "manifest.files"):
            if not files:
                v.error("empty_manifest", "manifest.files", "at least one frozen file is required")
            paths = set()
            for index, entry in enumerate(files):
                where = "manifest.files[{}]".format(index)
                if not v.obj(entry, where, ("path", "sha256")):
                    continue
                if v.string(entry.get("path"), where + ".path"):
                    try:
                        resolved = (Path(path).resolve().parent / entry["path"]).resolve()
                        if resolved in paths:
                            v.error("duplicate_manifest_path", where + ".path", "same resolved path listed more than once")
                        paths.add(resolved)
                    except (OSError, ValueError, RuntimeError) as exc:
                        v.error("invalid_manifest_path", where + ".path", str(exc))
                digest = entry.get("sha256")
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    v.error("invalid_sha256", where + ".sha256", "expected exactly 64 lowercase hexadecimal characters")
    result["errors"] = v.errors
    if v.errors:
        return result
    for entry in data["files"]:
        frozen_path = (Path(path).resolve().parent / entry["path"]).resolve()
        finding = {"path": entry["path"], "resolved_path": str(frozen_path), "expected_sha256": entry["sha256"], "actual_sha256": None, "matches": False}
        try:
            digest = hashlib.sha256()
            with frozen_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            finding["actual_sha256"] = digest.hexdigest()
            finding["matches"] = finding["actual_sha256"] == entry["sha256"]
        except (OSError, ValueError, RuntimeError) as exc:
            finding["error"] = str(exc)
        result["files"].append(finding)
    result["status"] = "verified" if all(item["matches"] for item in result["files"]) else "mismatch"
    return result


def review_issues(record):
    problems = []
    if not record["independently_reviewed"]:
        problems.append("independent_review_pending")
    other = record.get("independent_reviewer")
    if other is None:
        problems.append("independent_reviewer_missing")
    elif other["id"].strip().casefold() == record["reviewer"]["id"].strip().casefold():
        problems.append("reviewer_ids_not_distinct")
    for field in ("capture", "downstream", "core_counterexample", "fixed_adoption"):
        if record[field]["verdict"] == "insufficient":
            problems.append(field + "_insufficient")
    return problems


def key_ref(record, **extra):
    return dict({"case_id": record["case_id"], "repeat": record["repeat"]}, **extra)


def empty_result(manifest, external_protocol=None):
    return {
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "conclusion": "insufficient",
        "input_valid": False,
        "evaluation_complete": False,
        "validation_errors": [],
        "completeness_issues": [],
        "manifest": manifest,
        "protocol_binding": read_protocol(None) if external_protocol is None else external_protocol,
        "gate": {
            "passed": False,
            "threshold_kind": "predeclared_engineering_rule_not_statistical_significance",
            "minimum_stable_critical_cases": MIN_STABLE_CRITICAL_CASES,
            "conditions": {},
        },
        "counts": {},
        "findings": {},
        "case_patterns": [],
        "audit_rows": [],
        "limitations": [
            "Annotations, evidence semantics, reviewer independence, and independent executions are not verified by this tool.",
            "Source and evidence references are checked as nonempty strings; their contents are not automatically judged or authenticated.",
            "Fixed-context paths only diagnose adoption and never count as evidence that eliciting information worked.",
            "The decision rule is an engineering threshold, not an estimate of general efficacy or statistical significance.",
            "Passing fixtures validates the evaluator's bookkeeping, not the skill under evaluation.",
            "External protocol binding checks matrix dimensions; explanatory fields are preserved but not semantically executed.",
            "File hashes cannot establish when a protocol or manifest was frozen, authenticate its provenance, or prove runtime loading.",
        ],
    }


def evaluate(data, manifest=None, external_protocol=None):
    if manifest is None:
        manifest = check_manifest(None)
    if external_protocol is None:
        external_protocol = read_protocol(None)
    result = empty_result(manifest, external_protocol)
    errors = validate(data)
    result["validation_errors"] = errors
    if manifest["status"] == "invalid":
        result["validation_errors"] += manifest["errors"]
    if result["validation_errors"]:
        return result

    result["input_valid"] = True
    binding = bind_protocol(external_protocol, data["protocol"], manifest)
    result["protocol_binding"] = binding
    if binding["errors"]:
        result["validation_errors"].extend(binding["errors"])
        result["input_valid"] = False
    result["versions"] = data["versions"]
    result["protocol"] = data["protocol"]
    cases = {case["id"]: case["kind"] for case in data["cases"]}
    records = {(row["case_id"], row["repeat"]): row for row in data["records"]}
    expected = []
    for case_id in sorted(cases):
        repeat_field = "fixed_repeats" if cases[case_id] == "fixed_context" else "main_repeats"
        expected.extend((case_id, repeat) for repeat in data["protocol"][repeat_field])
    missing = [{"case_id": case_id, "repeat": repeat} for case_id, repeat in expected if (case_id, repeat) not in records]
    for row in missing:
        result["completeness_issues"].append(dict(row, code="missing_record"))

    tallies = {kind: {field: {value: 0 for value in comparison_verdicts(kind, field)} for field in ("capture", "downstream")} for kind in KINDS}
    burden = {kind: {version: {metric: 0 for metric in METRICS} for version in VERSIONS} for kind in KINDS}
    findings = {
        "missing_records": missing,
        "incomplete_reviews": [],
        "reliable_core_counterexamples": [],
        "control_added_blocking_or_repeat_confirmation": [],
        "fixed_adoption_regressions": [],
        "severe_violations": {version: [] for version in VERSIONS},
        "stable_critical_end_to_end_gain_cases": [],
        "stable_critical_capture_gain_cases": [],
        "stable_critical_downstream_gain_cases": [],
        "stable_main_burden_gain_cases": [],
        "main_cases_with_varying_repeats": [],
        "main_rows_with_burden_increases": [],
    }
    complete_rows = 0
    insufficient_judgments = 0
    fixed_tally = {verdict: 0 for verdict in VERDICTS}
    for key in sorted(records):
        row = records[key]
        kind = cases[row["case_id"]]
        problems = review_issues(row)
        if problems:
            finding = key_ref(row, issues=problems)
            findings["incomplete_reviews"].append(finding)
            result["completeness_issues"].append(dict(finding, code="review_incomplete"))
        else:
            complete_rows += 1
        for field in ("capture", "downstream", "core_counterexample", "fixed_adoption"):
            insufficient_judgments += row[field]["verdict"] == "insufficient"
        for field in ("capture", "downstream"):
            tallies[kind][field][row[field]["verdict"]] += 1
        for version in VERSIONS:
            for metric in METRICS:
                burden[kind][version][metric] += row[version][metric]
            for violation in row[version]["severe_violations"]:
                findings["severe_violations"][version].append(key_ref(row, **violation))
        if row["core_counterexample"]["verdict"] == "yes":
            findings["reliable_core_counterexamples"].append(key_ref(row, evidence_refs=row["core_counterexample"]["evidence_refs"]))
        increased = [metric for metric in METRICS if row["candidate"][metric] > row["baseline"][metric]]
        if kind != "fixed_context" and increased:
            findings["main_rows_with_burden_increases"].append(key_ref(row, metrics=increased))
        if kind == "control":
            added = [metric for metric in ("blocking_rounds", "repeated_confirmations") if metric in increased]
            if added:
                findings["control_added_blocking_or_repeat_confirmation"].append(key_ref(row, metrics=added, source_refs=row["source_refs"]))
        if kind == "fixed_context":
            fixed_tally[row["fixed_adoption"]["verdict"]] += 1
            if row["fixed_adoption"]["verdict"] == "baseline":
                findings["fixed_adoption_regressions"].append(key_ref(row, evidence_refs=row["fixed_adoption"]["evidence_refs"]))
        audit = dict(row)
        audit["kind"] = kind
        audit["review_complete"] = not problems
        audit["burden_candidate_minus_baseline"] = {metric: row["candidate"][metric] - row["baseline"][metric] for metric in METRICS}
        result["audit_rows"].append(audit)

    for case_id in sorted(cases):
        kind = cases[case_id]
        repeats = data["protocol"]["fixed_repeats" if kind == "fixed_context" else "main_repeats"]
        rows = [records[(case_id, repeat)] for repeat in repeats if (case_id, repeat) in records]
        complete = len(rows) == len(repeats) and all(not review_issues(row) for row in rows)
        pattern = {
            "case_id": case_id,
            "kind": kind,
            "expected_repeats": repeats,
            "observed_repeats": [row["repeat"] for row in rows],
            "review_complete": complete,
            "stable_main_capture_gain": False,
            "stable_main_downstream_gain": False,
            "stable_main_end_to_end_gain": False,
            "stable_main_burden_gain": False,
            "main_verdicts_vary_between_repeats": False,
        }
        if kind != "fixed_context" and complete:
            capture_gain = all(row["capture"]["verdict"] == "candidate" for row in rows)
            downstream_gain = all(row["downstream"]["verdict"] == "candidate" for row in rows)
            burden_gain = all(
                all(row["candidate"][metric] <= row["baseline"][metric] for metric in METRICS)
                and any(row["candidate"][metric] < row["baseline"][metric] for metric in METRICS)
                for row in rows
            )
            varies = any(len({row[field]["verdict"] for row in rows if row[field]["verdict"] != "not_applicable"}) > 1 for field in ("capture", "downstream"))
            pattern.update(
                stable_main_capture_gain=capture_gain,
                stable_main_downstream_gain=downstream_gain,
                stable_main_end_to_end_gain=capture_gain and downstream_gain,
                stable_main_burden_gain=burden_gain,
                main_verdicts_vary_between_repeats=varies,
            )
            if kind == "critical":
                if capture_gain:
                    findings["stable_critical_capture_gain_cases"].append(case_id)
                if downstream_gain:
                    findings["stable_critical_downstream_gain_cases"].append(case_id)
                if capture_gain and downstream_gain:
                    findings["stable_critical_end_to_end_gain_cases"].append(case_id)
            if burden_gain:
                findings["stable_main_burden_gain_cases"].append(case_id)
            if varies:
                findings["main_cases_with_varying_repeats"].append(case_id)
        result["case_patterns"].append(pattern)

    manifest_ok = manifest["status"] in ("not_requested", "verified")
    if not manifest_ok:
        result["completeness_issues"].append({"code": "frozen_manifest_not_verified", "status": manifest["status"]})
    protocol_ok = binding["status"] == "matched"
    protocol_covered = binding["manifest_coverage"] in ("not_requested", "matched")
    if not protocol_ok:
        result["completeness_issues"].append({"code": "external_protocol_not_bound", "status": binding["status"]})
    if not protocol_covered:
        result["completeness_issues"].append({"code": "external_protocol_not_covered_by_manifest", "status": binding["manifest_coverage"]})
    complete = not result["completeness_issues"] and result["input_valid"]
    result["evaluation_complete"] = complete
    stable_count = len(findings["stable_critical_end_to_end_gain_cases"])
    conditions = {
        "external_protocol_bound_and_matches": protocol_ok,
        "external_protocol_covered_if_manifest_requested": protocol_covered,
        "complete_independently_reviewed_matrix": complete,
        "at_least_two_stable_critical_end_to_end_gains": stable_count >= MIN_STABLE_CRITICAL_CASES,
        "no_reliable_core_counterexample": not findings["reliable_core_counterexamples"],
        "no_control_added_blocking_or_repeat_confirmation": not findings["control_added_blocking_or_repeat_confirmation"],
        "no_fixed_adoption_regression": not findings["fixed_adoption_regressions"],
        "no_candidate_severe_violations": not findings["severe_violations"]["candidate"],
        "frozen_files_intact_if_manifest_requested": manifest_ok,
    }
    # Unknown judgments must never make their individual negative-check gates
    # look satisfied, even though the matrix-completeness gate also blocks.
    for field, condition in (
        ("core_counterexample", "no_reliable_core_counterexample"),
        ("fixed_adoption", "no_fixed_adoption_regression"),
    ):
        if conditions[condition] and any(row[field]["verdict"] == "insufficient" for row in records.values()):
            conditions[condition] = None
    if missing or findings["incomplete_reviews"]:
        for condition in (
            "no_reliable_core_counterexample",
            "no_control_added_blocking_or_repeat_confirmation",
            "no_fixed_adoption_regression",
            "no_candidate_severe_violations",
        ):
            if conditions[condition] is True:
                conditions[condition] = None
    result["gate"]["conditions"] = conditions
    result["gate"]["passed"] = all(value is True for value in conditions.values())
    result["counts"] = {
        "case_counts": data["protocol"]["case_counts"],
        "expected_records": len(expected),
        "external_expected_records": (
            (binding["requirements"]["case_counts"]["critical"] + binding["requirements"]["case_counts"]["control"]) * len(binding["requirements"]["main_repeats"])
            + binding["requirements"]["case_counts"]["fixed_context"] * len(binding["requirements"]["fixed_repeats"])
        ) if binding["requirements"] is not None else None,
        "observed_records": len(records),
        "review_complete_records": complete_rows,
        "missing_records": len(missing),
        "incomplete_review_records": len(findings["incomplete_reviews"]),
        "insufficient_judgments": insufficient_judgments,
        "stable_critical_end_to_end_gain_cases": stable_count,
        "stable_critical_capture_gain_cases": len(findings["stable_critical_capture_gain_cases"]),
        "stable_critical_downstream_gain_cases": len(findings["stable_critical_downstream_gain_cases"]),
        "stable_main_burden_gain_cases": len(findings["stable_main_burden_gain_cases"]),
        "reliable_core_counterexample_rows": len(findings["reliable_core_counterexamples"]),
        "control_regression_rows": len(findings["control_added_blocking_or_repeat_confirmation"]),
        "fixed_adoption_regression_rows": len(findings["fixed_adoption_regressions"]),
        "severe_violations": {name: len(findings["severe_violations"][name]) for name in VERSIONS},
        "verdicts_by_kind": tallies,
        "applicable_judgment_counts_by_kind": {
            kind: {field: sum(tallies[kind][field][verdict] for verdict in VERDICTS)
                   for field in ("capture", "downstream")}
            for kind in KINDS
        },
        "fixed_adoption_verdicts": fixed_tally,
        "burden_totals_by_kind": burden,
    }
    result["findings"] = findings
    main_rows = [row for row in records.values() if cases[row["case_id"]] != "fixed_context"]
    applicable = {field: [row[field]["verdict"] for row in main_rows if row[field]["verdict"] != "not_applicable"]
                  for field in ("capture", "downstream")}
    all_downstream_ties = all(verdict == "tie" for verdict in applicable["downstream"])
    all_capture_ties = all(verdict == "tie" for verdict in applicable["capture"])
    all_main_ties = all_downstream_ties and all_capture_ties
    no_main_capture_loss = all(row["capture"]["verdict"] != "baseline" for row in main_rows)
    no_main_downstream_loss = all(row["downstream"]["verdict"] != "baseline" for row in main_rows)
    burden_same = all(row["candidate"][metric] == row["baseline"][metric] for row in main_rows for metric in METRICS)
    blocked = any(conditions[name] is False for name in (
        "no_reliable_core_counterexample",
        "no_control_added_blocking_or_repeat_confirmation",
        "no_fixed_adoption_regression",
        "no_candidate_severe_violations",
    ))
    if not complete:
        conclusion = "insufficient"
    elif blocked:
        conclusion = "regression_or_constraint_failure"
    elif result["gate"]["passed"]:
        conclusion = "limited_end_to_end_gain"
    elif stable_count:
        conclusion = "local_end_to_end_gain_below_threshold"
    elif findings["stable_critical_capture_gain_cases"] and all_downstream_ties and no_main_capture_loss:
        conclusion = "capture_only_gain"
    elif findings["stable_critical_downstream_gain_cases"] and all_capture_ties and no_main_downstream_loss:
        conclusion = "downstream_only_gain"
    elif all_main_ties and findings["stable_main_burden_gain_cases"] and not findings["main_rows_with_burden_increases"]:
        conclusion = "burden_only_gain"
    elif all_main_ties and burden_same:
        conclusion = "parity"
    else:
        conclusion = "unstable_or_mixed"
    result["conclusion"] = conclusion
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("annotations", help="schema-v1 annotated comparison JSON")
    parser.add_argument("--protocol", help="external protocol JSON required to bind and pass the adoption gate")
    parser.add_argument("--manifest", help="optional separately frozen schema-v1 SHA-256 manifest")
    parser.add_argument("--output", help="also write the exact JSON result to this file")
    args = parser.parse_args(argv)
    manifest = check_manifest(args.manifest)
    external_protocol = read_protocol(args.protocol)
    try:
        data = read_json(args.annotations)
    except (OSError, UnicodeError, ValueError) as exc:
        result = empty_result(manifest, external_protocol)
        result["validation_errors"].append(issue("annotations_read_error", str(args.annotations), str(exc)))
    else:
        result = evaluate(data, manifest, external_protocol)
    exit_code = 2 if not result["input_valid"] else (0 if result["evaluation_complete"] else 1)
    serialized = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            Path(args.output).write_text(serialized, encoding="utf-8")
        except (OSError, ValueError) as exc:
            result["conclusion"] = "insufficient"
            result["evaluation_complete"] = False
            result["gate"]["passed"] = False
            result["validation_errors"].append(issue("output_write_error", str(args.output), str(exc)))
            serialized = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
            exit_code = 2
    sys.stdout.write(serialized)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

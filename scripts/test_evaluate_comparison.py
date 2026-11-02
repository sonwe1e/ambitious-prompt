#!/usr/bin/env python3
"""Portable synthetic CLI regressions; these do not evaluate any real skill.

Run: python3 -B scripts/test_evaluate_comparison.py --output-dir /tmp/evaluator-tests
Only synthetic fixtures/results under --output-dir are written. The evaluator
is located beside this script; no workspace-specific path is assumed.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', required=True, help='Scratch directory for generated synthetic fixtures and results')
args = parser.parse_args()
ROOT = Path(args.output_dir).expanduser().resolve()
SCRIPT = Path(__file__).resolve().with_name('evaluate_comparison.py')
ROOT.mkdir(parents=True, exist_ok=True)


def judgment(verdict, reference):
    return {'verdict': verdict, 'evidence_refs': [reference] if verdict != 'not_applicable' else []}


def make_data():
    cases = [{'id': prefix + str(n), 'kind': kind}
             for kind, prefix, count in [('critical', 'K', 4), ('control', 'C', 4), ('fixed_context', 'F', 2)]
             for n in range(1, count + 1)]
    records = []
    for case in cases:
        for repeat in ([1] if case['kind'] == 'fixed_context' else [1, 2]):
            ref = 'synthetic/' + case['id'] + '/r' + str(repeat)
            outcome = {'information_requests': 0, 'blocking_rounds': 0,
                       'repeated_confirmations': 0, 'severe_violations': []}
            records.append({
                'case_id': case['id'], 'repeat': repeat,
                'reviewer': {'id': 'synthetic-reviewer-a', 'kind': 'independent_model'},
                'independently_reviewed': True,
                'independent_reviewer': {'id': 'synthetic-reviewer-b', 'kind': 'human'},
                'source_refs': [ref + '#paired-output'],
                'capture': judgment('tie', ref + '#capture'),
                'downstream': judgment('tie', ref + '#downstream'),
                'core_counterexample': judgment('no', ref + '#core'),
                'fixed_adoption': judgment('tie' if case['kind'] == 'fixed_context' else 'not_applicable', ref + '#adoption'),
                'candidate': copy.deepcopy(outcome), 'baseline': copy.deepcopy(outcome),
            })
    return {'schema_version': 1, 'versions': {'candidate': 'synthetic-v13', 'baseline': 'synthetic-v12'},
            'protocol': {'case_counts': {'critical': 4, 'control': 4, 'fixed_context': 2},
                         'main_repeats': [1, 2], 'fixed_repeats': [1]},
            'cases': cases, 'records': records}


def row(data, case_id, repeat=1):
    return next(item for item in data['records'] if item['case_id'] == case_id and item['repeat'] == repeat)


def wins(data, cases=('K1', 'K2'), fields=('capture', 'downstream')):
    for case_id in cases:
        for repeat in [1, 2]:
            for field in fields:
                row(data, case_id, repeat)[field]['verdict'] = 'candidate'
    return data


def set_nested(data, case, field, subfield, value, repeat=1):
    row(data, case, repeat)[field][subfield] = value


violation = {'kind': 'hard_constraint', 'description': 'SYNTHETIC: omitted the explicitly required offline operation.',
             'evidence_refs': ['synthetic/K1/r1#requires-network-despite-offline-constraint']}
base = make_data()
positive = wins(make_data())
protocol_path = ROOT / 'synthetic-protocol.json'
protocol_payload = dict(copy.deepcopy(base['protocol']), protocol_version=1,
                        explanation='SYNTHETIC protocol; keep this extra explanation.',
                        limits=['Synthetic fixtures cannot establish skill efficacy.'])
protocol_path.write_text(json.dumps(protocol_payload, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
protocol_digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
protocol_manifest_entry = {'path': protocol_path.name, 'sha256': protocol_digest}
tests = []


def add(name, start, change, conclusion, exit_code=0, check=None, manifest=None, protocol=protocol_path):
    data = copy.deepcopy(start)
    change(data)
    tests.append((name, data, conclusion, exit_code, check, manifest, protocol))


add('valid_gain', positive, lambda d: None, 'limited_end_to_end_gain', check=lambda r: r['counts']['stable_critical_end_to_end_gain_cases'] == 2 and r['counts']['expected_records'] == 18)
add('missing_row', positive, lambda d: d['records'].pop(), 'insufficient', 1, lambda r: r['counts']['missing_records'] == 1)
add('duplicate_record', positive, lambda d: d['records'].append(copy.deepcopy(d['records'][0])), 'insufficient', 2)
add('single_task_gain', base, lambda d: wins(d, ('K1',)), 'local_end_to_end_gain_below_threshold', check=lambda r: r['counts']['stable_critical_end_to_end_gain_cases'] == 1)
add('control_blocking_regression', positive, lambda d: set_nested(d, 'C1', 'candidate', 'blocking_rounds', 1), 'regression_or_constraint_failure', check=lambda r: r['counts']['control_regression_rows'] == 1)
add('control_reconfirmation_regression', positive, lambda d: set_nested(d, 'C1', 'candidate', 'repeated_confirmations', 1), 'regression_or_constraint_failure')
add('candidate_hard_constraint_failure', positive, lambda d: set_nested(d, 'K1', 'candidate', 'severe_violations', [violation]), 'regression_or_constraint_failure')
add('baseline_failure_is_reported_not_blocking', positive, lambda d: set_nested(d, 'K1', 'baseline', 'severe_violations', [violation]), 'limited_end_to_end_gain', check=lambda r: r['counts']['severe_violations'] == {'candidate': 0, 'baseline': 1})
add('unknown_verdict', positive, lambda d: set_nested(d, 'K1', 'capture', 'verdict', 'unknown'), 'insufficient', 2)
add('explicit_insufficient', positive, lambda d: set_nested(d, 'K4', 'downstream', 'verdict', 'insufficient'), 'insufficient', 1)
add('reliable_core_counterexample', positive, lambda d: set_nested(d, 'K3', 'core_counterexample', 'verdict', 'yes'), 'regression_or_constraint_failure')
add('unresolved_core_counterexample', positive, lambda d: set_nested(d, 'K3', 'core_counterexample', 'verdict', 'insufficient'), 'insufficient', 1, lambda r: r['gate']['conditions']['no_reliable_core_counterexample'] is None)
add('fixed_adoption_regression', positive, lambda d: set_nested(d, 'F1', 'fixed_adoption', 'verdict', 'baseline'), 'regression_or_constraint_failure')
add('fixed_adoption_insufficient', positive, lambda d: set_nested(d, 'F1', 'fixed_adoption', 'verdict', 'insufficient'), 'insufficient', 1)
add('not_reviewed', positive, lambda d: row(d, 'K4').update(independently_reviewed=False), 'insufficient', 1)
add('second_reviewer_missing', positive, lambda d: row(d, 'K4').pop('independent_reviewer'), 'insufficient', 1)
add('same_reviewer_id', positive, lambda d: row(d, 'K4')['independent_reviewer'].update(id=' SYNTHETIC-REVIEWER-A '), 'insufficient', 1)
add('boolean_is_not_count', positive, lambda d: set_nested(d, 'K1', 'candidate', 'information_requests', True), 'insufficient', 2)
add('string_is_not_count', positive, lambda d: set_nested(d, 'K1', 'candidate', 'information_requests', '1'), 'insufficient', 2)
add('negative_count', positive, lambda d: set_nested(d, 'K1', 'candidate', 'information_requests', -1), 'insufficient', 2)
add('unknown_case_kind', positive, lambda d: d['cases'][0].update(kind='unspecified'), 'insufficient', 2)
add('duplicate_case', positive, lambda d: d['cases'].append(copy.deepcopy(d['cases'][0])), 'insufficient', 2)
add('declared_case_count_mismatch', positive, lambda d: d['protocol']['case_counts'].update(critical=3), 'insufficient', 2)
add('undeclared_repeat', positive, lambda d: row(d, 'K1').update(repeat=3), 'insufficient', 2)
add('one_main_repeat_cannot_pass', positive, lambda d: d['protocol'].update(main_repeats=[1]), 'insufficient', 2)
add('parity', base, lambda d: None, 'parity')
add('capture_only', base, lambda d: wins(d, ('K1',), ('capture',)), 'capture_only_gain')
add('downstream_only', base, lambda d: wins(d, ('K1',), ('downstream',)), 'downstream_only_gain')


def burden_gain(data):
    for repeat in [1, 2]:
        row(data, 'K1', repeat)['baseline'].update(information_requests=1, blocking_rounds=1)


add('burden_only', base, burden_gain, 'burden_only_gain')


def burden_tradeoff(data):
    for repeat in [1, 2]:
        row(data, 'K1', repeat)['baseline'].update(information_requests=1)
        row(data, 'K1', repeat)['candidate'].update(blocking_rounds=1)


add('burden_tradeoff_has_no_weighted_win', base, burden_tradeoff, 'unstable_or_mixed')


def unstable(data):
    for case_id in ['K1', 'K2']:
        for field in ['capture', 'downstream']:
            row(data, case_id, 1)[field]['verdict'] = 'candidate'


add('wins_not_repeated', base, unstable, 'unstable_or_mixed', check=lambda r: r['counts']['stable_critical_end_to_end_gain_cases'] == 0)


def fixed_only(data):
    for case_id in ['F1', 'F2']:
        for field in ['capture', 'downstream', 'fixed_adoption']:
            row(data, case_id)[field]['verdict'] = 'candidate'
        row(data, case_id)['baseline'].update(information_requests=2, blocking_rounds=1)


add('fixed_path_never_proves_elicitation', base, fixed_only, 'parity', check=lambda r: r['counts']['stable_critical_end_to_end_gain_cases'] == 0 and r['counts']['stable_main_burden_gain_cases'] == 0)
add('bad_reviewer_kind', positive, lambda d: row(d, 'K1')['reviewer'].update(kind='model'), 'insufficient', 2)
add('empty_evidence', positive, lambda d: set_nested(d, 'K1', 'capture', 'evidence_refs', []), 'insufficient', 2)
add('source_refs_wrong_type', positive, lambda d: row(d, 'K1').update(source_refs='not-an-array'), 'insufficient', 2)
add('string_is_not_bool', positive, lambda d: row(d, 'K1').update(independently_reviewed='true'), 'insufficient', 2)
add('unknown_field_rejected', positive, lambda d: row(d, 'K1').update(weighted_score=100), 'insufficient', 2)
add('no_keyword_judgment', base, lambda d: row(d, 'K1').update(source_refs=['SYNTHETIC: candidate understood the user perfectly; three questions???']), 'parity')


def control_downstream_na(data):
    for record in data['records']:
        if record['case_id'].startswith('C'):
            record['downstream'] = judgment('not_applicable', '')


def fixed_capture_downstream_na(data):
    for record in data['records']:
        if record['case_id'].startswith('F'):
            record['capture'] = judgment('not_applicable', '')
            record['downstream'] = judgment('not_applicable', '')


add('control_downstream_na_allowed', positive, control_downstream_na, 'limited_end_to_end_gain',
    check=lambda r: r['counts']['applicable_judgment_counts_by_kind']['control'] == {'capture': 8, 'downstream': 0}
    and r['counts']['verdicts_by_kind']['control']['downstream']['not_applicable'] == 8)


def fixed_na_with_adoption_regression(data):
    fixed_capture_downstream_na(data)
    row(data, 'F1')['fixed_adoption']['verdict'] = 'baseline'


add('fixed_na_keeps_adoption_gate', positive, fixed_na_with_adoption_regression, 'regression_or_constraint_failure',
    check=lambda r: r['counts']['applicable_judgment_counts_by_kind']['fixed_context'] == {'capture': 0, 'downstream': 0}
    and r['counts']['fixed_adoption_regression_rows'] == 1)


def forbidden_critical_na(data):
    for field in ['capture', 'downstream']:
        row(data, 'K1')[field] = judgment('not_applicable', '')


add('critical_na_rejected', positive, forbidden_critical_na, 'insufficient', 2)


def burden_with_na(data):
    control_downstream_na(data)
    fixed_capture_downstream_na(data)
    burden_gain(data)


add('burden_only_uses_applicable_ties', base, burden_with_na, 'burden_only_gain',
    check=lambda r: r['counts']['stable_critical_capture_gain_cases'] == 0
    and r['counts']['stable_critical_downstream_gain_cases'] == 0
    and r['counts']['stable_critical_end_to_end_gain_cases'] == 0
    and r['counts']['verdicts_by_kind']['control']['downstream']['candidate'] == 0)

frozen = ROOT / 'synthetic-frozen.txt'
frozen.write_text('synthetic frozen version\n', encoding='utf-8')
digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
manifest_payload = {'schema_version': 1, 'files': [{'path': frozen.name, 'sha256': digest}, protocol_manifest_entry]}
manifest_path = ROOT / 'manifest-match.json'
manifest_path.write_text(json.dumps(manifest_payload), encoding='utf-8')
mismatch_path = ROOT / 'manifest-mismatch.json'
mismatch_path.write_text(json.dumps({'schema_version': 1, 'files': [{'path': frozen.name, 'sha256': '0' * 64}, protocol_manifest_entry]}), encoding='utf-8')
empty_manifest_path = ROOT / 'manifest-empty.json'
empty_manifest_path.write_text('{"schema_version":1,"files":[]}', encoding='utf-8')
missing_file_manifest = ROOT / 'manifest-file-absent.json'
missing_file_manifest.write_text(json.dumps({'schema_version': 1, 'files': [{'path': 'does-not-exist.txt', 'sha256': digest}, protocol_manifest_entry]}), encoding='utf-8')
bad_hash_manifest = ROOT / 'manifest-bad-hash.json'
bad_hash_manifest.write_text(json.dumps({'schema_version': 1, 'files': [{'path': frozen.name, 'sha256': 'invalid'}]}), encoding='utf-8')
duplicate_path_manifest = ROOT / 'manifest-duplicate-path.json'
duplicate_path_manifest.write_text(json.dumps({'schema_version': 1, 'files': [manifest_payload['files'][0], {'path': './' + frozen.name, 'sha256': digest}]}), encoding='utf-8')
add('manifest_verified', positive, lambda d: None, 'limited_end_to_end_gain', manifest=manifest_path, check=lambda r: r['manifest']['status'] == 'verified')
add('manifest_drift', positive, lambda d: None, 'insufficient', 1, manifest=mismatch_path)
add('manifest_missing', positive, lambda d: None, 'insufficient', 2, manifest=ROOT / 'absent-manifest.json')
add('manifest_empty', positive, lambda d: None, 'insufficient', 2, manifest=empty_manifest_path)
add('manifest_frozen_file_absent', positive, lambda d: None, 'insufficient', 1, manifest=missing_file_manifest)
add('manifest_bad_hash', positive, lambda d: None, 'insufficient', 2, manifest=bad_hash_manifest)
add('manifest_duplicate_path', positive, lambda d: None, 'insufficient', 2, manifest=duplicate_path_manifest)

# The original 52 checks remain: these 49 fixtures, two parser checks below,
# and the deterministic-order check. New regression cases follow separately.
original_names = {test[0] for test in tests}
assert len(original_names) + 3 == 52


def shrink_matrix(data):
    retained = {'K1', 'K2', 'C1', 'F1'}
    data['cases'] = [case for case in data['cases'] if case['id'] in retained]
    data['records'] = [record for record in data['records'] if record['case_id'] in retained]
    data['protocol']['case_counts'] = {'critical': 2, 'control': 1, 'fixed_context': 1}


add('shrunk_matrix_rejected_against_external_protocol', positive, shrink_matrix, 'insufficient', 1,
    manifest=manifest_path,
    check=lambda r: r['manifest']['status'] == 'verified'
    and r['protocol_binding']['status'] == 'mismatch'
    and r['counts']['observed_records'] == 7 and r['counts']['external_expected_records'] == 18
    and r['counts']['stable_critical_end_to_end_gain_cases'] == 2)


def different_fixed_repeats(data):
    data['protocol']['fixed_repeats'] = [1, 2]
    for case_id in ['F1', 'F2']:
        extra = copy.deepcopy(row(data, case_id))
        extra['repeat'] = 2
        data['records'].append(extra)


add('repeat_settings_must_match_external_protocol', positive, different_fixed_repeats, 'insufficient', 1,
    manifest=manifest_path,
    check=lambda r: r['input_valid'] and r['protocol_binding']['status'] == 'mismatch'
    and r['protocol_binding']['mismatches'][0]['field'] == 'fixed_repeats'
    and r['counts']['observed_records'] == 20 and r['counts']['external_expected_records'] == 18)
add('unbound_without_protocol', positive, lambda d: None, 'insufficient', 1, protocol=None,
    check=lambda r: r['input_valid'] and r['protocol_binding']['status'] == 'unbound'
    and r['counts']['observed_records'] == 18)
add('verified_manifest_does_not_replace_protocol_binding', positive, lambda d: None, 'insufficient', 1,
    protocol=None, manifest=manifest_path,
    check=lambda r: r['manifest']['status'] == 'verified' and r['protocol_binding']['status'] == 'unbound')
add('missing_external_protocol_file', positive, lambda d: None, 'insufficient', 2,
    protocol=ROOT / 'missing-external-protocol.json',
    check=lambda r: r['protocol_binding']['status'] == 'invalid' and r['counts']['observed_records'] == 18)
corrupt_protocol = ROOT / 'corrupt-protocol.json'
corrupt_protocol.write_text('{"case_counts":', encoding='utf-8')
add('corrupt_external_protocol', positive, lambda d: None, 'insufficient', 2, protocol=corrupt_protocol,
    check=lambda r: r['protocol_binding']['status'] == 'invalid')
missing_field_protocol = ROOT / 'protocol-missing-field.json'
missing_field_protocol.write_text(json.dumps({'main_repeats': [1, 2], 'fixed_repeats': [1]}), encoding='utf-8')
add('external_protocol_missing_required_field', positive, lambda d: None, 'insufficient', 2, protocol=missing_field_protocol)
invalid_repeats_protocol = ROOT / 'protocol-invalid-main-repeats.json'
invalid_repeats_protocol.write_text(json.dumps(dict(protocol_payload, main_repeats=[1])), encoding='utf-8')
add('external_protocol_invalid_main_repeats', positive, lambda d: None, 'insufficient', 2, protocol=invalid_repeats_protocol)
add('external_protocol_explanations_preserved', positive, lambda d: None, 'limited_end_to_end_gain',
    manifest=manifest_path,
    check=lambda r: r['protocol_binding']['document'] == protocol_payload
    and r['protocol_binding']['manifest_coverage'] == 'matched')
uncovered_manifest = ROOT / 'manifest-without-protocol.json'
uncovered_manifest.write_text(json.dumps({'schema_version': 1, 'files': [manifest_payload['files'][0]]}), encoding='utf-8')
add('manifest_must_cover_bound_protocol', positive, lambda d: None, 'insufficient', 1, manifest=uncovered_manifest,
    check=lambda r: r['manifest']['status'] == 'verified' and r['protocol_binding']['manifest_coverage'] == 'not_listed')
other_protocol = ROOT / 'different-protocol.json'
other_protocol.write_text(json.dumps(dict(protocol_payload, explanation='A different protocol file.')), encoding='utf-8')
add('different_protocol_cannot_borrow_manifest', positive, lambda d: None, 'insufficient', 1,
    protocol=other_protocol, manifest=manifest_path,
    check=lambda r: r['manifest']['status'] == 'verified' and r['protocol_binding']['status'] == 'matched'
    and r['protocol_binding']['manifest_coverage'] == 'not_listed')
add('isolated_surrogate_stdout_and_output', positive, lambda d: d['versions'].update(candidate='candidate-\ud800'),
    'limited_end_to_end_gain', check=lambda r: r['versions']['candidate'] == 'candidate-\ud800')
add('isolated_surrogate_validation_error_json', positive, lambda d: d.update({'\ud800': 'unexpected field'}),
    'insufficient', 2, check=lambda r: any('\ud800' in error['location'] for error in r['validation_errors']))

summary = []
for name, data, expected, expected_code, check, manifest, protocol in tests:
    path = ROOT / (name + '.json')
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    output_path = ROOT / (name + '.result.json')
    command = [sys.executable, '-B', str(SCRIPT), str(path), '--output', str(output_path)]
    if protocol is not None:
        command += ['--protocol', str(protocol)]
    if manifest:
        command += ['--manifest', str(manifest)]
    completed = subprocess.run(command, text=True, capture_output=True)
    assert not completed.stderr, (name, completed.stderr)
    result = json.loads(completed.stdout)
    assert completed.stdout.isascii(), (name, 'result is not ASCII-safe JSON')
    assert output_path.read_text(encoding='utf-8') == completed.stdout, name
    assert completed.returncode == expected_code, (name, completed.returncode, result)
    assert result['conclusion'] == expected, (name, result['conclusion'], expected)
    assert result['gate']['passed'] == (expected == 'limited_end_to_end_gain'), name
    if check:
        assert check(result), (name, 'custom check failed', result)
    summary.append({'fixture': name, 'conclusion': result['conclusion'], 'exit_code': completed.returncode, 'passed': True})

# Parser-level checks cannot be represented by a Python dictionary.
for name, payload in [('duplicate_json_key', '{"schema_version":1,"schema_version":1}'),
                      ('non_json_nan', '{"schema_version":NaN}')]:
    path = ROOT / (name + '.json')
    path.write_text(payload, encoding='utf-8')
    completed = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path), '--protocol', str(protocol_path)], text=True, capture_output=True)
    result = json.loads(completed.stdout)
    assert completed.returncode == 2 and result['conclusion'] == 'insufficient' and not result['gate']['passed'], name
    summary.append({'fixture': name, 'conclusion': result['conclusion'], 'exit_code': completed.returncode, 'passed': True})

# Input array order must not alter the exact deterministic output.
shuffled = copy.deepcopy(positive)
shuffled['records'].reverse()
shuffled['cases'].reverse()
path = ROOT / 'reordered.json'
path.write_text(json.dumps(shuffled), encoding='utf-8')
completed = subprocess.run([sys.executable, '-B', str(SCRIPT), str(path), '--protocol', str(protocol_path)], text=True, capture_output=True)
assert completed.returncode == 0
assert completed.stdout == (ROOT / 'valid_gain.result.json').read_text(encoding='utf-8')
summary.append({'fixture': 'deterministic_under_row_order', 'passed': True})

# Exercise both stdout-only and the second serialization after --output fails.
surrogate_input = ROOT / 'isolated_surrogate_stdout_and_output.json'
command = [sys.executable, '-B', str(SCRIPT), str(surrogate_input), '--protocol', str(protocol_path)]
completed = subprocess.run(command, text=True, capture_output=True)
result = json.loads(completed.stdout)
assert not completed.stderr and completed.returncode == 0 and completed.stdout.isascii()
assert result['versions']['candidate'] == 'candidate-\ud800'
assert completed.stdout == (ROOT / 'isolated_surrogate_stdout_and_output.result.json').read_text(encoding='utf-8')
summary.append({'fixture': 'isolated_surrogate_stdout_only', 'passed': True})
completed = subprocess.run(command + ['--output', str(ROOT)], text=True, capture_output=True)
result = json.loads(completed.stdout)
assert not completed.stderr and completed.returncode == 2 and completed.stdout.isascii()
assert result['versions']['candidate'] == 'candidate-\ud800' and result['conclusion'] == 'insufficient'
assert any(error['code'] == 'output_write_error' for error in result['validation_errors'])
summary.append({'fixture': 'isolated_surrogate_output_write_error_json', 'passed': True})

(ROOT / 'fixture-summary.json').write_text(json.dumps(summary, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'synthetic_fixture_checks_passed': len(summary),
                  'original_fixture_checks': 52, 'new_regression_checks': len(summary) - 52,
                  'fixture_directory': str(ROOT), 'results': summary}, ensure_ascii=True, indent=2))

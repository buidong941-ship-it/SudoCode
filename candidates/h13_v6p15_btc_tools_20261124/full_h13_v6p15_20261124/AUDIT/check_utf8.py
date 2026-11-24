"""Run on Kaggle: verify H13 text integrity, repair scope and release hashes."""
import hashlib
import json
from pathlib import Path
import re
import sys

RELEASE = Path(__file__).resolve().parents[1]
ROOT = RELEASE.parents[3]
OLD = RELEASE.with_name('h13_revised_20261122')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def strings(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, path + '.' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings(child, path + f'[{index}]')
    elif isinstance(value, str):
        yield path, value


def damaged(text):
    # Sentence-final question marks are valid; embedded/repeated ones and U+FFFD are not.
    return bool(re.search(r'\?(?=\w)|\?\?|\ufffd', text))


def changes(before, after, path=''):
    assert type(before) is type(after), path
    if isinstance(before, dict):
        assert before.keys() == after.keys(), path
        for key in before:
            yield from changes(before[key], after[key], path + '.' + key)
    elif isinstance(before, list):
        assert len(before) == len(after), path
        for index, (a, b) in enumerate(zip(before, after)):
            yield from changes(a, b, path + f'[{index}]')
    elif before != after:
        assert isinstance(before, str) and '?' in before, path
        yield path, before, after


def main():
    manifest = json.loads((RELEASE / 'manifest.json').read_text(encoding='utf-8'))
    ledger = json.loads((RELEASE / 'AUDIT/UTF8_REPAIR_LEDGER.json').read_text(encoding='utf-8'))
    expected = {(x['file'], x['path'], x['before'], x['after']) for x in ledger['changes']}
    actual, errors, original_bad = set(), [], set()
    original_runtime_bad = set()
    counts = {'scenarios': 0, 'calls': 0, 'customer_turns': 0}
    for path in sorted((RELEASE / 'scenarios').glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8', errors='strict'))
        old = json.loads((OLD / 'scenarios' / path.name).read_text(encoding='utf-8'))
        for field, value in strings(old):
            if damaged(value):
                original_bad.add(path.stem)
                if field.startswith('.calls.'):
                    original_runtime_bad.add(path.stem)
        for field, value in strings(data):
            if damaged(value):
                errors.append({'file': path.name, 'field': field, 'value': value})
        actual.update((path.name, field, a, b) for field, a, b in changes(old, data))
        assert sha(path) == manifest['scenario_sha256'][path.stem], path
        counts['scenarios'] += 1
        counts['calls'] += len(data['calls'])
        counts['customer_turns'] += sum(len(c.get('customer_turns', [])) for c in data['calls'].values())
    assert actual == expected, 'Undeclared or unapplied text repairs'
    assert len(original_runtime_bad) == 10, original_runtime_bad
    assert len(original_bad) == 16, original_bad
    assert counts == manifest['counts'], counts
    assert not damaged('Em cho chị hỏi giá bao nhiêu?')
    assert damaged('ch?a l?n ??n')
    for name, digest in manifest['audit_sha256'].items():
        assert sha(RELEASE / 'AUDIT' / name) == digest, name
    lock = json.loads((RELEASE / 'AUDIT/SOURCE_LOCK.json').read_text(encoding='utf-8'))
    for name, digest in lock['protected_btc_sha256'].items():
        assert sha(ROOT / name) == digest, name
    canary = ROOT / 'candidates/jev_write_gate_v15/canary_h13_revised_20261122_utf8'
    canary_lock = json.loads((canary / 'LOCK.json').read_text(encoding='utf-8'))
    assert canary_lock['source_release_manifest_sha256'] == sha(RELEASE / 'manifest.json')
    for sid, digest in canary_lock['scenario_sha256'].items():
        assert sha(canary / 'scenarios' / (sid + '.json')) == digest == manifest['scenario_sha256'][sid]
    for name, digest in canary_lock['files_sha256'].items():
        assert sha(canary / name) == digest, name
    # Corrupted strings in the repair ledger are retained as evidence, never runtime input.
    for path in (RELEASE / 'AUDIT').glob('*.md'):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if damaged(line):
                errors.append({'file': path.name, 'line': number, 'value': line})
    result = {'status': 'PASS' if not errors else 'FAIL', 'counts': counts,
              'repaired_fields': len(actual), 'source_corrupted_scenarios': sorted(original_bad),
              'source_corrupted_runtime_scenarios': sorted(original_runtime_bad),
              'errors': errors, 'manifest_sha256': sha(RELEASE / 'manifest.json'),
              'protected_btc_files': len(lock['protected_btc_sha256'])}
    Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())

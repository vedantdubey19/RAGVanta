"""Offline release invariants. Does not claim hosted controls have been exercised."""
from pathlib import Path
import json
import yaml

root = Path(__file__).resolve().parents[1]
blueprint = yaml.safe_load((root / 'render.yaml').read_text())['services'][0]
assert blueprint['numInstances'] == 1
assert blueprint['healthCheckPath'] == '/health'
assert blueprint['disk']['mountPath'] == '/workspace/.runtime'
assert not (root / '.env').exists() or '.env' in (root / '.gitignore').read_text().splitlines()
assert 'innerHTML' not in (root / 'app/web/app.js').read_text()
assert 'eval(' not in (root / 'app/web/app.js').read_text()
for path in ('docs/security.md','docs/rulesandlimits.md','docs/architecture.md','docs/design.md',
             'docs/deploy-render.md','docs/incident-response.md'):
    assert (root/path).is_file(), path
for name in ('scenarios.jsonl','held_out.jsonl'):
    records = [json.loads(line) for line in (root/'datasets'/name).read_text().splitlines() if line]
    assert len({r['scenario_id'] for r in records}) == len(records)
print('Release configuration invariants passed')

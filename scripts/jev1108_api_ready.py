"""Load named credentials from environment/Kaggle Secrets, then STOP without API calls."""
import json
import os
from pathlib import Path
import sys
required = ('DEEPSEEK_API_KEY', 'TYPESAFE_API_KEY')
try:
    from kaggle_secrets import UserSecretsClient
    secrets = UserSecretsClient()
except ImportError:
    secrets = None
for name in required:
    if not os.environ.get(name) and secrets:
        try:
            value = secrets.get_secret(name)
            if value: os.environ[name] = value
        except Exception:
            pass
status = {'loaded': {name: bool(os.environ.get(name)) for name in required},
          'api_calls': 0, 'stopped_at': 'credential_loading', 'requires_agreement_before_live_run': True}
if len(sys.argv) > 1:
    p = Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(status, indent=2), encoding='utf-8')
print(json.dumps(status))

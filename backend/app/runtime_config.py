"""Non-secret, versioned runtime choices; read once, included in build identity."""
import json
from pathlib import Path
CONFIG = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))

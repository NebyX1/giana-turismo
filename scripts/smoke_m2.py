import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app, CONSENTS


def main():
    with app.test_client() as c:
        no_consent = c.post("/api/web/search", json={"session_id": "s", "request_id": "missing"})
        created = c.post("/api/web/consent", json={"session_id": "s", "query": "horario actual de Salus"}).get_json()
        consented = c.post("/api/web/search", json={"session_id": "s", "request_id": created["request_id"]})
        CONSENTS[("s", "expired")] = {"query": "x", "expires_at": time.time() - 1}
        expired = c.post("/api/web/search", json={"session_id": "s", "request_id": "expired"})
    result = {"missing_consent": no_consent.status_code, "created": bool(created.get("request_id")), "consented_status": consented.status_code, "expired_consent": expired.status_code}
    print(json.dumps(result, ensure_ascii=False))
    Path(ROOT / "reports/m2_smoke.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result["missing_consent"] == 403 and result["created"] and result["expired_consent"] == 403 else 1)


if __name__ == "__main__": main()

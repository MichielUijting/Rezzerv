from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import engine  # noqa: E402
from app.testing.almost_out_self_test import run_almost_out_backend_self_test  # noqa: E402
from app.testing.product_enrichment_self_test import run_product_enrichment_backend_self_test  # noqa: E402


def main() -> int:
    target = (sys.argv[1] if len(sys.argv) > 1 else 'almost-out').strip().lower()
    if target not in {'almost-out', 'almost_out', 'almost-out-self-test', 'product-enrichment', 'product_enrichment', 'product-enrichment-self-test'}:
        print(f'Onbekende testtarget: {target}', file=sys.stderr)
        return 2
    if target in {'product-enrichment', 'product_enrichment', 'product-enrichment-self-test'}:
        report = run_product_enrichment_backend_self_test(engine)
    else:
        report = run_almost_out_backend_self_test(engine)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get('failed_count', 0) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

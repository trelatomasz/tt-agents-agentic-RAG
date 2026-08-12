import asyncio
import json
from pathlib import Path

from gpc_rag.catalog import Catalog
from gpc_rag.generator import DeterministicGenerator
from gpc_rag.service import NoEvidenceError, RagService


async def main() -> int:
    service = RagService(Catalog.load("data/catalog.json"), DeterministicGenerator(), 3600, 4)
    cases = [json.loads(line) for line in Path("evals/dataset.jsonl").read_text().splitlines()]
    passed = 0
    for case in cases:
        try:
            response = await service.ask(case["query"], case["id"], 1)
            ok = not case["must_abstain"] and case["expected_part"] in {c.part_id for c in response.citations}
        except NoEvidenceError:
            ok = case["must_abstain"]
        passed += ok
        print(json.dumps({"id": case["id"], "passed": ok}))
    score = passed / len(cases)
    print(json.dumps({"metric": "release_gate_pass_rate", "value": score, "threshold": 1.0}))
    return 0 if score == 1.0 else 1


raise SystemExit(asyncio.run(main()))

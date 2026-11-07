"""Logs every request as one JSON line and summarises the log: latency, tokens and estimated cost."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config


class CallLog:
    def __init__(self, path=config.LOG_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # the API can handle several requests at once

    def write(self, **record):
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def records(self):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def stats(self):
        records = self.records()
        ok = [r for r in records if r.get("status") == "ok"]
        latencies = sorted(r["latency_ms"] for r in ok)
        by_model = {}
        for r in ok:
            model = by_model.setdefault(r["model"], {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                                                     "estimated_cost_usd": 0.0})
            model["requests"] += 1
            model["input_tokens"] += r["input_tokens"]
            model["output_tokens"] += r["output_tokens"]
            model["estimated_cost_usd"] = round(model["estimated_cost_usd"] + r["estimated_cost_usd"], 6)
        return {
            "requests": len(records),
            "errors": len(records) - len(ok),
            "latency_ms": {
                "avg": round(sum(latencies) / len(latencies)) if latencies else None,
                "p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
            },
            "tokens": {
                "input": sum(r["input_tokens"] for r in ok),
                "output": sum(r["output_tokens"] for r in ok),
            },
            "estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in ok), 6),
            "by_model": by_model,
            "note": "Costs are estimated at paid-tier list prices; requests on the free tier are not billed.",
        }

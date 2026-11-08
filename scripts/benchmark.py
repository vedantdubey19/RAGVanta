import argparse
import json
from pathlib import Path
from app.config import Settings
from app.evaluation import run_experiment
from app.service import Laboratory

parser = argparse.ArgumentParser()
parser.add_argument("--split", choices=["development", "held_out"], default="development")
parser.add_argument("--limit", type=int, default=50)
parser.add_argument("--offset", type=int, default=0)
parser.add_argument("--output", type=Path, default=Path("results/latest.json"))
args = parser.parse_args()
if not 1 <= args.limit <= 50:
    parser.error("limit must be between 1 and 50")
report = run_experiment(Laboratory(Settings()), args.split, args.limit, args.offset)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2))
print(json.dumps({"id": report["id"], "status": report["status"], "metrics": report["metrics"]}, indent=2))
raise SystemExit(0 if report["status"] == "completed" else 1)

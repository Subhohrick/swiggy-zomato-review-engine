"""Runs the whole Review-to-Roadmap pipeline in one go (for n8n).

Steps: engine.py -> explore.py -> classify_groq.py -> roadmap.py
- Each step's output goes to logs/run_<date>.log (this is your audit trail).
- Each week's roadmap is archived in history/ so you can compare weeks.
- The only thing printed to the screen is one JSON summary, which n8n reads.

Test it yourself first:   python run_pipeline.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
STEPS = ["engine.py", "explore.py", "classify_groq.py", "roadmap.py"]
MUST_SUCCEED = {"engine.py", "explore.py"}   # if these fail, stop the run
TOP_N = 5

stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
(HERE / "logs").mkdir(exist_ok=True)
(HERE / "history").mkdir(exist_ok=True)
log_path = HERE / "logs" / f"run_{stamp}.log"

env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}  # write to log live
steps_status = {}
with open(log_path, "w", encoding="utf-8") as log:
    for step in STEPS:
        log.write(f"\n===== {step} =====\n")
        log.flush()
        print(f"Running {step} ...", file=sys.stderr, flush=True)
        r = subprocess.run([sys.executable, step], cwd=HERE, env=env,
                           stdout=log, stderr=subprocess.STDOUT)
        steps_status[step] = "ok" if r.returncode == 0 else f"failed (code {r.returncode})"
        if r.returncode != 0 and step in MUST_SUCCEED:
            break

result = {"run_at": stamp, "steps": steps_status, "log_file": str(log_path), "top": {}}

roadmap_file = HERE / "roadmap.csv"
if steps_status.get("roadmap.py") == "ok" and roadmap_file.exists():
    rm = pd.read_csv(roadmap_file)
    rm.to_csv(HERE / "history" / f"roadmap_{stamp}.csv", index=False, encoding="utf-8-sig")
    lines = [f"Review-to-Roadmap report ({stamp})", ""]
    if steps_status.get("classify_groq.py") != "ok":
        lines += ["NOTE: classification did not finish (probably the Groq daily limit).",
                  "This report uses the reviews classified so far.", ""]
    for brand, part in rm.groupby("brand"):
        part = part.sort_values("rank").head(TOP_N)
        result["top"][brand] = part[["rank", "label", "per_1000", "avg_severity",
                                     "vs_competitor", "priority"]].to_dict("records")
        lines.append(f"{brand.upper()} - top {TOP_N} fixes")
        for _, r in part.iterrows():
            vs = f"{r['vs_competitor']}x competitor" if pd.notna(r["vs_competitor"]) else "competitor ~0"
            lines.append(f"  {r['rank']}. {r['label']} - {r['per_1000']} per 1,000 reviews, "
                         f"severity {r['avg_severity']}, {vs}")
        lines.append("")
    result["summary_text"] = "\n".join(lines)
else:
    result["summary_text"] = (f"Review-to-Roadmap run FAILED ({stamp}).\n"
                              f"Steps: {steps_status}\nSee log: {log_path}")

# NaN is not valid JSON, so turn it into null
print(json.dumps(result, ensure_ascii=False, default=str).replace("NaN", "null"))
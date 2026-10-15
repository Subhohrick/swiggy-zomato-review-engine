"""Step 2: classify reviews with Groq (FREE tier, no card).

Run:   python classify_groq.py
Progress is saved after every batch to progress.jsonl, so if it stops
(rate limit, internet, Ctrl+C) just run it again and it continues.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

# ---------------- SETTINGS ----------------
RUN_ALL = True          # False = test sample (100 per brand). True = all reviews.
SAMPLE_PER_BRAND = 300
BATCH_SIZE = 10          # small batches stay under the free tokens-per-minute limit
WAIT_BETWEEN = 20        # seconds between batches
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
PROGRESS_FILE = "progress_all.jsonl" if RUN_ALL else "progress_sample.jsonl"
OUTPUT_FILE = "classified_all.csv" if RUN_ALL else "classified_sample.csv"
# ------------------------------------------

ISSUES = [
    "Delivery delayed / ETA wrong",
    "Missing or wrong items",
    "Food cold, spilled or poorly packed",
    "Refund not received or rejected",
    "Customer support unhelpful",
    "High platform / delivery fee or surge",
    "Membership issue (Swiggy One / Zomato Gold)",
    "Delivery partner behaviour",
    "Order cancelled after payment",
    "Coupon or offer not applied",
    "App bug (payment failure, crash, login/OTP)",
    "Restaurant food quality",
    "Cash on delivery unavailable",
    "Service not available in area",
    "Location / GPS issue",
    "Language support request",
    "Too many ads or notifications",
    "Scam or unexplained charge",
    "Unable to cancel order",
    "Want more offers or discounts",
    "Cancellation fee charged (customer cancelled)",
    "Menu prices higher than restaurant",
    "Offers or discounts reduced",
]

# Merge near-duplicate labels the model invents into known ones.
# Add to this after reading the "New labels" list at the end of each run.
MERGE = {
    "Add cash on delivery option": "Cash on delivery unavailable",
    "Limited geographic coverage": "Service not available in area",
    "Location service inaccurate": "Location / GPS issue",
    "App bug (location not working)": "Location / GPS issue",
    "Add national language support": "Language support request",
    "Add Hindi language support": "Language support request",
    "Too many ads / intrusive advertising": "Too many ads or notifications",
    "Scam or fraudulent charge": "Scam or unexplained charge",
    "Deceptive platform behavior": "Scam or unexplained charge",
    "Incorrect portion size": "Missing or wrong items",
    "Cannot cancel order within allowed time": "Unable to cancel order",
    "No cancellation option": "Unable to cancel order",
    "Discount request": "Want more offers or discounts",
    "Request for discount or offer": "Want more offers or discounts",
    "More offers needed": "Want more offers or discounts",
    "Request more easy-to-apply coupons": "Want more offers or discounts",
    "Cashback incentive suggestion": "Want more offers or discounts",
    "Misleading menu images": "Misleading food photos",
    "Low quantity for price": "Missing or wrong items",
    
}
VAGUE = {"General poor service", "General app dissatisfaction", "Poor service", "Poor service quality"}
SYSTEM = f"""You analyze Indian food-delivery app reviews (Swiggy, Zomato).
Reviews may be in English, Hindi or Hinglish.

Known issue labels:
{json.dumps(ISSUES, indent=1)}

Return a JSON object: {{"results": [ ...one object per review... ]}}
Each object:
{{"n": <same n as input>,
  "text_en": "<English translation, or original if already English>",
  "service": "food" | "instamart" | "dineout" | "other",
  "is_complaint": true | false,
  "issues": [{{"label": "...", "category": "bug|ux|pricing|delivery|support|restaurant_quality|feature_request",
              "severity": 1-5, "is_new": false}}]}}

Rules:
- Reuse a known label EXACTLY as written whenever the meaning matches, even if wording differs.
- Only create a new label (is_new: true) for a genuinely different problem; keep it under 8 words.
- A review can have several issues. Praise-only reviews get "issues": [].
- Complaints about a restaurant's cooking use "Restaurant food quality".
- Severity: 1 = minor annoyance, 5 = lost money or could not use the app.
- Never create vague labels like "general dissatisfaction" or "poor service".
  If no specific issue fits, return "issues": [].
- Before creating a new label, check whether a known label covers the same
  problem in different words. Prefer the known label.
- "Order cancelled after payment" is ONLY when the platform or restaurant
  cancelled. If the customer cancelled and was charged, use
  "Cancellation fee charged (customer cancelled)".
- Use "Scam or unexplained charge" ONLY when no specific cause is given.
  If the review names a cause (late delivery, missing refund, fee), label that cause.
- A concrete suggestion (e.g. "add cashback", "add COD") is a feature request:
  give it a short label with category "feature_request", never "none".
Return ONLY the JSON object."""

# ---- API key ----
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)
key = os.getenv("GROQ_API_KEY")
if not key:
    raise SystemExit(f"GROQ_API_KEY not found. Looked in: {env_path} (exists: {env_path.exists()})")
client = Groq(api_key=key)

# ---- Reviews to classify ----
df = pd.read_csv("reviews_clean.csv")
if RUN_ALL:
    data = df.reset_index(drop=True)
else:
    data = pd.concat(
        g.sample(min(SAMPLE_PER_BRAND, len(g)), random_state=42) for _, g in df.groupby("brand")
    ).reset_index(drop=True)

# ---- Resume: skip reviews already done ----
done = {}
if Path(PROGRESS_FILE).exists():
    with open(PROGRESS_FILE, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            done[rec["id"]] = rec
todo = data[~data["id"].isin(done)]
total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
print(f"{len(data)} reviews total, {len(done)} already done, {len(todo)} to go "
      f"({total_batches} batches, ~{total_batches * WAIT_BETWEEN // 60 + 1} min)\n")

# ---- Classify ----
for b, start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
    batch = todo.iloc[start:start + BATCH_SIZE]
    items = [{"n": int(i), "text": str(t)[:800]} for i, t in zip(batch.index, batch["text"])]

    parsed = None
    for attempt in range(4):
        model = MODELS[0] if attempt < 2 else MODELS[1]
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            parsed = json.loads(resp.choices[0].message.content)["results"]
            break
        except Exception as e:
            wait = 30 * (attempt + 1)
            print(f"  Batch {b} [{model}]: {str(e)[:200]}\n  -> retrying in {wait}s")
            time.sleep(wait)

    if parsed:
        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
            for r in parsed:
                if r.get("n") in batch.index:
                    r["id"] = batch.loc[r["n"], "id"]
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    done[r["id"]] = r
        print(f"Batch {b}/{total_batches}: ok ({model})")
    else:
        print(f"Batch {b}/{total_batches}: FAILED, skipped (run again later to retry)")
    time.sleep(WAIT_BETWEEN)

# ---- Flatten: one row per (review, issue) ----
src_by_id = data.set_index("id")
rows = []
for rid, r in done.items():
    if rid not in src_by_id.index:
        continue
    src = src_by_id.loc[rid]
    issues = r.get("issues") or [{"label": "none", "category": "none", "severity": 0, "is_new": False}]
    for iss in issues:
        label = MERGE.get(iss.get("label"), iss.get("label"))
        if label in VAGUE:
            label = "none"
        rows.append({
            "id": rid, "brand": src["brand"], "rating": src["rating"], "date": src["date"],
            "text": src["text"], "text_en": r.get("text_en"), "service": r.get("service"),
            "is_complaint": r.get("is_complaint"), "label": label,
            "category": iss.get("category"), "severity": iss.get("severity"),
            "is_new": label not in ISSUES and label != "none",
        })

if not rows:
    raise SystemExit("No results came back. Check the error messages above.")

out = pd.DataFrame(rows)
out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
print(f"\nSaved {out['id'].nunique()} classified reviews to {OUTPUT_FILE}")

new_labels = out[out["is_new"]]["label"].value_counts()
if len(new_labels):
    print("\nNew labels the model proposed (add to ISSUES or MERGE):")
    print(new_labels.to_string())
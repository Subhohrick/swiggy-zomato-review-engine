"""Step 2: classify reviews with Gemini (FREE tier).

Setup (PowerShell, inside .venv):
    python -m pip install google-genai
    $env:GEMINI_API_KEY = "your-key-from-aistudio"
"""
from dotenv import load_dotenv
load_dotenv()
import json
import time

import pandas as pd
from google import genai
from google.genai import types

# Tried in order; if one is overloaded, the next is used.
# Fill this from your model list (without the "models/" prefix).
MODELS = ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3-flash"]

SAMPLE_PER_BRAND = 100   # keep small while tuning the prompt
BATCH_SIZE = 20

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
]

SYSTEM = f"""You analyze Indian food-delivery app reviews (Swiggy, Zomato).
Reviews may be in English, Hindi or Hinglish.

Known issue labels:
{json.dumps(ISSUES, indent=1)}

For each review, return an object:
{{"n": <same n as input>,
  "text_en": "<English translation, or original if already English>",
  "service": "food" | "instamart" | "dineout" | "other",
  "is_complaint": true | false,
  "issues": [{{"label": "...", "category": "bug|ux|pricing|delivery|support|restaurant_quality|feature_request",
              "severity": 1-5, "is_new": false}}]}}

Rules:
- Reuse a known label whenever the meaning matches, even if wording differs.
- Only create a new label (is_new: true) for a genuinely different problem; keep it under 8 words.
- A review can have several issues. Praise-only reviews get "issues": [].
- Complaints about a restaurant's cooking use "Restaurant food quality".
- Severity: 1 = minor annoyance, 5 = lost money or could not use the app.
Return ONLY a JSON array, no markdown, no commentary."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

df = pd.read_csv("reviews_clean.csv")
sample = pd.concat(
    g.sample(min(SAMPLE_PER_BRAND, len(g)), random_state=42) for _, g in df.groupby("brand")
).reset_index(drop=True)

results = []
for start in range(0, len(sample), BATCH_SIZE):
    batch = sample.iloc[start:start + BATCH_SIZE]
    # Short numeric keys so the model can't garble the long Play Store review IDs
    items = [{"n": int(i), "text": str(t)[:1000]} for i, t in zip(batch.index, batch["text"])]
    raw = None
    for attempt in range(4):
        model = MODELS[attempt % len(MODELS)]
        try:
            resp = client.models.generate_content(
                model=model,
                contents=json.dumps(items, ensure_ascii=False),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            raw = (resp.text or "").strip().removeprefix("```json").removesuffix("```").strip()
            break
        except Exception as e:
            code = getattr(e, "code", "?")
            print(f"  {model}: error {code}, trying next in {10 * (attempt + 1)}s...")
            time.sleep(10 * (attempt + 1))

# Flatten: one row per (review, issue)
rows = []
for r in results:
    src = sample.loc[r["n"]]
    issues = r.get("issues") or [{"label": "none", "category": "none", "severity": 0, "is_new": False}]
    for iss in issues:
        rows.append({
            "id": src["id"], "brand": src["brand"], "rating": src["rating"],
            "text": src["text"], "text_en": r.get("text_en"), "service": r.get("service"),
            "is_complaint": r.get("is_complaint"), **iss,
        })
out = pd.DataFrame(rows)
out.to_csv("classified_sample.csv", index=False, encoding="utf-8-sig")
print(f"\nSaved {out['id'].nunique()} classified reviews to classified_sample.csv")

# Quick head-to-head: mentions per 1,000 food reviews
food = out[out["service"] == "food"]
totals = food.drop_duplicates("id").groupby("brand").size()
issues = food[food["label"] != "none"].drop_duplicates(["id", "label"])
table = issues.groupby(["label", "brand"]).size().unstack(fill_value=0)
rate = (table.div(totals, axis=1) * 1000).round(0)
if {"swiggy", "zomato"} <= set(rate.columns):
    rate["gap (swiggy/zomato)"] = (rate["swiggy"] / rate["zomato"].replace(0, float("nan"))).round(2)
    rate = rate.sort_values("swiggy", ascending=False)

print("\nMentions per 1,000 food reviews (small sample, directional only):")
print(rate.to_string())

new_labels = out[out["is_new"] == True]["label"].value_counts()
if len(new_labels):
    print("\nNew labels the model proposed (review these):")
    print(new_labels.to_string())
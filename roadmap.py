"""Step 3: turn classified reviews into a ranked product backlog per brand.

Run:   python roadmap.py                 (uses classified_all.csv if it exists)
Output: roadmap.csv  + top issues printed per brand
"""
from pathlib import Path
import pandas as pd

MIN_MENTIONS = 3     # ignore issues mentioned by fewer reviews than this
TOP_N = 5

src = "classified_all.csv" if Path("classified_all.csv").exists() else "classified_sample.csv"
df = pd.read_csv(src)
print(f"Using {src}: {df['id'].nunique()} reviews\n")

reviews_per_brand = df.drop_duplicates("id").groupby("brand").size()
issues = df[df["label"] != "none"].drop_duplicates(["id", "label"])

g = issues.groupby(["brand", "label"]).agg(
    mentions=("id", "nunique"),
    avg_severity=("severity", "mean"),
    category=("category", lambda s: s.mode().iat[0] if len(s.mode()) else ""),
    example=("text_en", "first"),
).reset_index()

g = g[g["label"].isin(issues.groupby("label")["id"].nunique().loc[lambda s: s >= MIN_MENTIONS].index)]
g["per_1000"] = g["mentions"] / g["brand"].map(reviews_per_brand) * 1000
g["avg_severity"] = g["avg_severity"].round(1)

# How much worse is this brand than its competitor on the same issue?
rate = g.pivot(index="label", columns="brand", values="per_1000").fillna(0)
def gap(row):
    other = rate.loc[row["label"]].drop(row["brand"])
    o = other.iloc[0] if len(other) else 0
    return round(row["per_1000"] / o, 1) if o else None
g["vs_competitor"] = g.apply(gap, axis=1)

# Priority = how often x how badly; boosted when you're worse than the competitor
boost = g["vs_competitor"].fillna(2).clip(lower=0.5, upper=3)
g["priority"] = (g["per_1000"] * g["avg_severity"] * boost / 100).round(1)

g["per_1000"] = g["per_1000"].round(0).astype(int)
g = g.sort_values(["brand", "priority"], ascending=[True, False])
g["rank"] = g.groupby("brand").cumcount() + 1
cols = ["brand", "rank", "label", "category", "mentions", "per_1000",
        "avg_severity", "vs_competitor", "priority", "example"]
g[cols].to_csv("roadmap.csv", index=False, encoding="utf-8-sig")

for brand, part in g.groupby("brand"):
    print(f"=== {brand.upper()} — top {TOP_N} fixes ===")
    for _, r in part.head(TOP_N).iterrows():
        vs = f"{r['vs_competitor']}x competitor" if pd.notna(r["vs_competitor"]) else "competitor ~0"
        print(f"{r['rank']}. {r['label']}  |  {r['per_1000']}/1000 reviews, "
              f"severity {r['avg_severity']}, {vs}, priority {r['priority']}")
    print()
print("Saved full backlog to roadmap.csv")
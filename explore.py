"""Step 1: sanity-check and clean the scraped Swiggy/Zomato reviews."""
import pandas as pd

df = pd.read_csv("swiggy_zomato_reviews.csv")
print("Total rows scraped:", len(df))

# Remove duplicates (en/hi fetches can overlap)
dups = df.duplicated("id").sum()
df = df.drop_duplicates("id")
print(f"Duplicates removed: {dups}")

df["text"] = df["text"].fillna("").astype(str).str.strip()
df["words"] = df["text"].str.split().str.len()
df["date"] = pd.to_datetime(df["date"])

print("\nReviews per brand / language:\n", df.groupby(["brand", "lang"]).size())
print("\nDate range per brand:\n", df.groupby("brand")["date"].agg(["min", "max"]))
print("\nRating distribution (% of each brand's reviews):\n",
      (pd.crosstab(df["brand"], df["rating"], normalize="index") * 100).round(1))
print("\nAverage rating:\n", df.groupby("brand")["rating"].mean().round(2))

short_pct = (df["words"] < 5).mean() * 100
print(f"\nShort reviews (<5 words, no usable signal): {short_pct:.1f}%")

clean = df[df["words"] >= 5]
clean.to_csv("reviews_clean.csv", index=False)
print(f"\nSaved {len(clean)} usable reviews to reviews_clean.csv")

# Eyeball real complaints before designing anything
print("\nSample low-rated reviews:")
for brand in clean["brand"].unique():
    low = clean[(clean["brand"] == brand) & (clean["rating"] <= 2)]
    print(f"\n--- {brand} ({len(low)} reviews rated 1-2) ---")
    for t in low.sample(min(5, len(low)), random_state=1)["text"]:
        print("-", t[:200])
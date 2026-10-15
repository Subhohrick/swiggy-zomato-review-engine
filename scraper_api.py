"""Tiny API that n8n calls to fetch the newest Swiggy/Zomato reviews."""
from fastapi import FastAPI
from google_play_scraper import Sort, reviews

APPS = {"swiggy": "in.swiggy.android", "zomato": "com.application.zomato"}
app = FastAPI()


@app.get("/reviews")
def get_reviews(count: int = 500):
    out, seen = [], set()
    for brand, app_id in APPS.items():
        for lang in ["en", "hi"]:
            result, _ = reviews(app_id, lang=lang, country="in", sort=Sort.NEWEST, count=count)
            for r in result:
                text = (r["content"] or "").strip()
                if r["reviewId"] in seen or len(text.split()) < 5:
                    continue
                seen.add(r["reviewId"])
                out.append({
                    "id": r["reviewId"],
                    "brand": brand,
                    "lang": lang,
                    "rating": r["score"],
                    "text": text,
                    "review_date": r["at"].isoformat(),
                })
    return out
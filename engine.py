# pip install google-play-scraper pandas
from google_play_scraper import reviews, Sort
import pandas as pd

apps = {"swiggy": "in.swiggy.android", "zomato": "com.application.zomato"}
rows = []
for brand, app_id in apps.items():
    for lang in ["en", "hi"]:                     # English + Hindi reviews
        result, _ = reviews(app_id, lang=lang, country="in",
                            sort=Sort.NEWEST, count=1000)
        for r in result:
            rows.append({"id": r["reviewId"], "brand": brand, "rating": r["score"],
                         "text": r["content"], "date": r["at"], "lang": lang})

pd.DataFrame(rows).to_csv("swiggy_zomato_reviews.csv", index=False)
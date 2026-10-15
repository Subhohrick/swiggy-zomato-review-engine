CREATE TABLE IF NOT EXISTS reviews (
  id          TEXT PRIMARY KEY,
  brand       TEXT NOT NULL,
  lang        TEXT,
  rating      INT,
  text        TEXT,
  review_date TIMESTAMP,
  service     TEXT,
  text_en     TEXT,
  analyzed    BOOLEAN DEFAULT false,
  fetched_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_issues (
  review_id TEXT REFERENCES reviews(id),
  label     TEXT,
  category  TEXT,
  severity  INT,
  is_new    BOOLEAN,
  PRIMARY KEY (review_id, label)
);

CREATE INDEX IF NOT EXISTS idx_reviews_analyzed ON reviews (analyzed);
CREATE INDEX IF NOT EXISTS idx_reviews_date     ON reviews (review_date);
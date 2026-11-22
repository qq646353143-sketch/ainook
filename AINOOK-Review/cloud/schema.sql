CREATE TABLE IF NOT EXISTS reset_snapshot (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wish_totals (
  platform TEXT PRIMARY KEY CHECK(platform IN ('codex', 'claude', 'grok')),
  total INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO wish_totals(platform) VALUES ('codex'), ('claude'), ('grok');
CREATE TABLE IF NOT EXISTS wish_batches (
  platform TEXT NOT NULL REFERENCES wish_totals(platform),
  batch_id TEXT NOT NULL,
  amount INTEGER NOT NULL CHECK(amount BETWEEN 1 AND 200),
  PRIMARY KEY(platform, batch_id)
);
CREATE TRIGGER IF NOT EXISTS count_wish AFTER INSERT ON wish_batches
BEGIN
  UPDATE wish_totals SET total = total + NEW.amount WHERE platform = NEW.platform;
END;

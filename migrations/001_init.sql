CREATE TABLE IF NOT EXISTS users (
 telegram_id INTEGER NOT NULL,
 chat_id INTEGER NOT NULL,
 username TEXT,
 display_name TEXT NOT NULL,
 stars INTEGER NOT NULL DEFAULT 0 CHECK(stars >= 0),
 wins INTEGER NOT NULL DEFAULT 0,
 games_played INTEGER NOT NULL DEFAULT 0,
 season_points INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (telegram_id, chat_id)
);
CREATE TABLE IF NOT EXISTS inventory (
 telegram_id INTEGER NOT NULL,
 chat_id INTEGER NOT NULL,
 item_id TEXT NOT NULL,
 qty INTEGER NOT NULL DEFAULT 0 CHECK(qty >= 0),
 PRIMARY KEY (telegram_id, chat_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_users_rank ON users(chat_id, stars DESC, wins DESC);

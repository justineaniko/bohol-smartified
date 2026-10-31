USE supplies_tracker;

CREATE TABLE IF NOT EXISTS api_keys (
  user_id      INT          NOT NULL PRIMARY KEY,
  key_hash     CHAR(64)     NOT NULL UNIQUE,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at DATETIME     NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

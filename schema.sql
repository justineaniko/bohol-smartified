-- Run these in TiDB's SQL editor, after: CREATE DATABASE supplies_tracker; USE supplies_tracker;

CREATE TABLE IF NOT EXISTS users (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  username        VARCHAR(30)  NOT NULL UNIQUE,
  display_name    VARCHAR(50)  NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,          -- one-way hash, never the real password
  session_version INT          NOT NULL DEFAULT 0, -- +1 signs out every device
  failed_attempts INT          NOT NULL DEFAULT 0,
  locked_until    DATETIME     NULL,               -- UTC
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recovery_codes (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  user_id   INT          NOT NULL,
  code_hash VARCHAR(255) NOT NULL,                 -- one-way hash of the code
  used_at   DATETIME     NULL,                     -- set when a code is used up
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

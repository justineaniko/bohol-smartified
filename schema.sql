-- Run once in TiDB's SQL editor:
--   CREATE DATABASE supplies_tracker;
--   USE supplies_tracker;
-- then paste everything below.

-- ---------------------------------------------------------------------------
-- Accounts (used by auth.py; already working)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  username        VARCHAR(30)  NOT NULL UNIQUE,
  display_name    VARCHAR(50)  NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,           -- one-way hash, never the real password
  is_admin        BOOLEAN      NOT NULL DEFAULT FALSE, -- first profile created becomes admin
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

-- Which profiles get which optional features (e.g. 'books')
CREATE TABLE IF NOT EXISTS user_features (
  user_id INT         NOT NULL,
  feature VARCHAR(30) NOT NULL,
  PRIMARY KEY (user_id, feature),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Supplies, food and clothes (inventory.py — your data layer)
-- ---------------------------------------------------------------------------
-- Places in the house. Each one gets ONE printed QR: /location/<slug>
CREATE TABLE IF NOT EXISTS locations (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  slug        VARCHAR(60)  NOT NULL UNIQUE,   -- goes in the QR URL: /location/<slug>
  name        VARCHAR(60)  NOT NULL,          -- 'Dining room fridge'
  shelf_count TINYINT      NULL,              -- NULL = no shelves
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  name                 VARCHAR(100) NOT NULL,
  category             VARCHAR(20)  NOT NULL,         -- 'products', 'food', 'clothes', 'other'
  owner_id             INT          NULL,             -- NULL = shared by the whole house
  quantity             INT          NOT NULL DEFAULT 0,
  threshold            INT          NOT NULL DEFAULT 0, -- low when quantity <= threshold
  low_stock_alert_sent BOOLEAN      NOT NULL DEFAULT FALSE,
  location_id          INT          NULL,             -- where it's kept (NULL = not set)
  shelf                TINYINT      NULL,             -- 1st, 2nd... shelf of that location
  expiry_date          DATE         NULL,             -- mainly food
  size                 VARCHAR(20)  NULL,             -- clothes
  color                VARCHAR(30)  NULL,             -- clothes
  season               VARCHAR(20)  NULL,             -- clothes: 'all', 'rainy', 'summer'...
  notes                TEXT         NULL,
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- Books (books.py — only profiles with the 'books' feature)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS books (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  owner_id    INT          NOT NULL,                  -- books are always private to one profile
  title       VARCHAR(200) NOT NULL,
  author      VARCHAR(120) NULL,
  status      VARCHAR(20)  NOT NULL DEFAULT 'to_read', -- 'to_read', 'reading', 'finished'
  rating      TINYINT      NULL,                      -- 1 to 5
  pages       INT          NULL,
  genre       VARCHAR(60)  NULL,
  started_on  DATE         NULL,
  finished_on DATE         NULL,
  notes       TEXT         NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Recipes (recipes.py — shared by the whole house)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  title        VARCHAR(150) NOT NULL,
  meal_type    VARCHAR(20)  NOT NULL,   -- 'breakfast', 'lunch', 'dinner', 'snack', 'dessert', 'drink'
  cuisine      VARCHAR(50)  NULL,
  prep_minutes INT          NULL,       -- total time
  servings     INT          NULL,
  tags         VARCHAR(255) NULL,       -- comma separated: 'quick, vegetarian'
  ingredients  TEXT         NOT NULL,   -- one ingredient per line
  steps        TEXT         NOT NULL,   -- one step per line
  created_by   INT          NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

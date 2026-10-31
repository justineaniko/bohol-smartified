CREATE TABLE IF NOT EXISTS users (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  username        VARCHAR(30)  NOT NULL UNIQUE,
  display_name    VARCHAR(50)  NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,
  is_admin        BOOLEAN      NOT NULL DEFAULT FALSE,
  session_version INT          NOT NULL DEFAULT 0,
  failed_attempts INT          NOT NULL DEFAULT 0,
  locked_until    DATETIME     NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recovery_codes (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  user_id   INT          NOT NULL,
  code_hash VARCHAR(255) NOT NULL,
  used_at   DATETIME     NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_features (
  user_id INT         NOT NULL,
  feature VARCHAR(30) NOT NULL,
  PRIMARY KEY (user_id, feature),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS locations (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  slug        VARCHAR(60)  NOT NULL UNIQUE,
  name        VARCHAR(60)  NOT NULL,
  shelf_count TINYINT      NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  name                 VARCHAR(100) NOT NULL,
  brand                VARCHAR(60)  NULL,
  pack_size            VARCHAR(30)  NULL,
  category             VARCHAR(20)  NOT NULL,
  owner_id             INT          NULL,
  quantity             INT          NOT NULL DEFAULT 0,
  threshold            INT          NOT NULL DEFAULT 0,
  low_stock_alert_sent BOOLEAN      NOT NULL DEFAULT FALSE,
  location_id          INT          NULL,
  shelf                TINYINT      NULL,
  expiry_date          DATE         NULL,
  notes                TEXT         NULL,
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS medicine (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  name                VARCHAR(100) NOT NULL,
  generic_name        VARCHAR(100) NOT NULL,
  strength            VARCHAR(30) NULL,
  owner_id            INT NULL,
  quantity            INT NOT NULL DEFAULT 0,
  threshold           INT NOT NULL DEFAULT 0,
  low_stock_alert_sent BOOLEAN NOT NULL DEFAULT FALSE,
  location_id         INT NULL,
  shelf               TINYINT NULL,
  expiry_date         DATE NULL,
  opened_on           DATE NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS books (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  owner_id    INT          NOT NULL,
  title       VARCHAR(200) NOT NULL,
  author      VARCHAR(120) NULL,
  status      VARCHAR(20)  NOT NULL DEFAULT 'to_read',
  rating      TINYINT      NULL,
  pages       INT          NULL,
  genre       VARCHAR(60)  NULL,
  started_on  DATE         NULL,
  finished_on DATE         NULL,
  notes       TEXT         NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recipes (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  title        VARCHAR(150) NOT NULL,
  meal_type    VARCHAR(20)  NOT NULL,
  cuisine      VARCHAR(50)  NULL,
  prep_minutes INT          NULL,
  servings     INT          NULL,
  tags         VARCHAR(255) NULL,
  ingredients  TEXT         NOT NULL,
  steps        TEXT         NOT NULL,
  created_by   INT          NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS hospital_supplies (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(100) NOT NULL,
  kind           VARCHAR(20)  NOT NULL,
  quantity       INT          NOT NULL DEFAULT 0,
  unit           VARCHAR(20)  NULL,
  size           VARCHAR(30)  NULL,
  item_condition VARCHAR(20)  NOT NULL DEFAULT 'sealed',
  status         VARCHAR(20)  NOT NULL DEFAULT 'in_stock',
  expiry_date    DATE         NULL,
  location_id    INT          NULL,
  shelf          TINYINT      NULL,
  notes          TEXT         NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

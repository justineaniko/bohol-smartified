CREATE TABLE IF NOT EXISTS locations (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  slug        VARCHAR(60)  NOT NULL UNIQUE,
  name        VARCHAR(60)  NOT NULL,
  shelf_count TINYINT      NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO locations (slug, name, shelf_count) VALUES
  ('dining-room-fridge', 'Dining room fridge', 5),
  ('pink-room-fridge',   'Pink room fridge',   5),
  ('big-freezer',        'Big freezer',        NULL);

ALTER TABLE items DROP INDEX qr_code_id;
ALTER TABLE items DROP COLUMN qr_code_id;

ALTER TABLE items DROP COLUMN location;
ALTER TABLE items ADD COLUMN location_id INT NULL;
ALTER TABLE items ADD COLUMN shelf TINYINT NULL;
ALTER TABLE items ADD CONSTRAINT fk_items_location
  FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL;

ALTER TABLE items ADD COLUMN brand VARCHAR(60) NULL;
ALTER TABLE items ADD COLUMN pack_size VARCHAR(30) NULL;

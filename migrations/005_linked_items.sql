USE supplies_tracker;

ALTER TABLE items ADD COLUMN link_id INT NULL;
ALTER TABLE items ADD COLUMN place_min INT NULL;
ALTER TABLE items ADD COLUMN move_alert_sent BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX idx_items_link ON items (link_id);

USE supplies_tracker;

ALTER TABLE items ADD COLUMN assigned_to INT NULL;
ALTER TABLE items ADD CONSTRAINT fk_items_assigned_to
  FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL;

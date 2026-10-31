USE supplies_tracker;

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

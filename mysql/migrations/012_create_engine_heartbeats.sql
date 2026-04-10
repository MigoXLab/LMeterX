-- Create engine_heartbeats table if it does not exist
CREATE TABLE IF NOT EXISTS `engine_heartbeats` (
  `engine_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_heartbeat` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`engine_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

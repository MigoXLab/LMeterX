-- Add stepped load configuration fields to common_tasks table
-- These fields support the stepped load test mode (similar to JMeter Ultimate Thread Group)

ALTER TABLE `common_tasks` ADD COLUMN `load_mode` varchar(16) NOT NULL DEFAULT 'fixed' COMMENT 'Load test mode: fixed or stepped' AFTER `duration`;

ALTER TABLE `common_tasks` ADD COLUMN `step_start_users` int(11) DEFAULT NULL COMMENT 'Stepped mode: initial number of users' AFTER `load_mode`;

ALTER TABLE `common_tasks` ADD COLUMN `step_increment` int(11) DEFAULT NULL COMMENT 'Stepped mode: users added per step' AFTER `step_start_users`;

ALTER TABLE `common_tasks` ADD COLUMN `step_duration` int(11) DEFAULT NULL COMMENT 'Stepped mode: duration of each step (seconds)' AFTER `step_increment`;

ALTER TABLE `common_tasks` ADD COLUMN `step_max_users` int(11) DEFAULT NULL COMMENT 'Stepped mode: maximum number of users' AFTER `step_duration`;

ALTER TABLE `common_tasks` ADD COLUMN `step_sustain_duration` int(11) DEFAULT NULL COMMENT 'Stepped mode: sustain duration at max users (seconds)' AFTER `step_max_users`;

-- Create table to persist real-time performance metrics collected during load tests.
-- This allows charts to remain viewable after the task finishes.

CREATE TABLE IF NOT EXISTS `common_task_realtime_metrics` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(40) NOT NULL COMMENT 'task id',
  `timestamp` double NOT NULL COMMENT 'unix timestamp of the metric snapshot',
  `current_users` int(11) NOT NULL DEFAULT '0' COMMENT 'concurrent users at this moment',
  `current_rps` float NOT NULL DEFAULT '0' COMMENT 'requests per second',
  `current_fail_per_sec` float NOT NULL DEFAULT '0' COMMENT 'failures per second',
  `avg_response_time` float NOT NULL DEFAULT '0' COMMENT 'average response time (ms)',
  `min_response_time` float NOT NULL DEFAULT '0' COMMENT 'min response time (ms)',
  `max_response_time` float NOT NULL DEFAULT '0' COMMENT 'max response time (ms)',
  `median_response_time` float NOT NULL DEFAULT '0' COMMENT 'median response time (ms)',
  `p90_response_time` float NOT NULL DEFAULT '0' COMMENT 'p90 response time (ms)',
  `total_requests` int(11) NOT NULL DEFAULT '0' COMMENT 'cumulative request count',
  `total_failures` int(11) NOT NULL DEFAULT '0' COMMENT 'cumulative failure count',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'row insertion time',
  PRIMARY KEY (`id`),
  KEY `idx_rt_metrics_task_id` (`task_id`),
  KEY `idx_rt_metrics_task_ts` (`task_id`, `timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

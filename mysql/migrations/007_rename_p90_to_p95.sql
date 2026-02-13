-- Rename p90 percentile columns to p95 across all relevant tables
-- This migration changes the 90th percentile response time to the 95th percentile

ALTER TABLE `task_results` CHANGE COLUMN `p90_latency` `p95_latency` float DEFAULT '0' COMMENT 'request 95% response time';

ALTER TABLE `common_task_results` CHANGE COLUMN `p90_latency` `p95_latency` float NOT NULL DEFAULT '0' COMMENT 'request 95% response time';

ALTER TABLE `common_task_realtime_metrics` CHANGE COLUMN `p90_response_time` `p95_response_time` float NOT NULL DEFAULT '0' COMMENT 'p95 response time (ms)';

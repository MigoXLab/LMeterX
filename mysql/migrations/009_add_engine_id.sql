-- Migration: Add engine_id column to tasks and common_tasks tables
-- This enables tracking which Engine instance executed each task

ALTER TABLE `tasks`
  ADD COLUMN `engine_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL
  COMMENT 'Engine instance ID that executed this task'
  AFTER `error_message`;

ALTER TABLE `tasks`
  ADD KEY `idx_engine_id` (`engine_id`);

ALTER TABLE `common_tasks`
  ADD COLUMN `engine_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL
  COMMENT 'Engine instance ID that executed this task'
  AFTER `error_message`;

ALTER TABLE `common_tasks`
  ADD KEY `idx_common_engine_id` (`engine_id`);

-- Migration: Remove unused fields
-- Description: Remove unused fields from tasks and common_tasks tables
-- Date: 2026-02-05

-- Remove system_prompt column from tasks table (unused field)
ALTER TABLE `tasks` DROP COLUMN `system_prompt`;

-- Remove stream_mode column from common_tasks table (reserved for compatibility but not actually used)
ALTER TABLE `common_tasks` DROP COLUMN  `stream_mode`;

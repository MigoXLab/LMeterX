-- Migration: Add soft delete support
-- Description: Add is_deleted field to tasks and common_tasks tables
-- Date: 2026-02-05

-- Add is_deleted column to tasks table
ALTER TABLE `tasks`
ADD COLUMN `is_deleted` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete flag: 0=active, 1=deleted' AFTER `error_message`,
ADD INDEX `idx_is_deleted` (`is_deleted`);

-- Add is_deleted column to common_tasks table
ALTER TABLE `common_tasks`
ADD COLUMN `is_deleted` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete flag: 0=active, 1=deleted' AFTER `error_message`,
ADD INDEX `idx_is_deleted` (`is_deleted`);

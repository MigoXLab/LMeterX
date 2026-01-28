-- Migration: Add created_by column to tasks and common_tasks
-- Date: 2026-01-14
-- Description: Store creator username for tasks listings

USE lmeterx;

-- Add created_by to tasks if missing
SET @col_exists_tasks = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'lmeterx'
      AND TABLE_NAME = 'tasks'
      AND COLUMN_NAME = 'created_by'
);

SET @sql_tasks = IF(
    @col_exists_tasks = 0,
    'ALTER TABLE `tasks` ADD COLUMN `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT ''Creator username'' AFTER `status`, ADD KEY `idx_created_by` (`created_by`)',
    'SELECT ''Column created_by already exists on tasks'' AS message'
);

PREPARE stmt1 FROM @sql_tasks;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

-- Add created_by to common_tasks if missing
SET @col_exists_common = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'lmeterx'
      AND TABLE_NAME = 'common_tasks'
      AND COLUMN_NAME = 'created_by'
);

SET @sql_common = IF(
    @col_exists_common = 0,
    'ALTER TABLE `common_tasks` ADD COLUMN `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT ''Creator username'' AFTER `status`, ADD KEY `idx_common_created_by` (`created_by`)',
    'SELECT ''Column created_by already exists on common_tasks'' AS message'
);

PREPARE stmt2 FROM @sql_common;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- Migration: Rename legacy task tables to explicit llm/http naming
-- NOTE:
--   - Existing data is preserved via RENAME TABLE.
--   - This script is idempotent and safe to run repeatedly.

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'tasks'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'llm_tasks'
  ),
  'RENAME TABLE `tasks` TO `llm_tasks`',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'task_results'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'llm_task_results'
  ),
  'RENAME TABLE `task_results` TO `llm_task_results`',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'common_tasks'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'http_tasks'
  ),
  'RENAME TABLE `common_tasks` TO `http_tasks`',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'common_task_results'
  ) AND NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'http_task_results'
  ),
  'RENAME TABLE `common_task_results` TO `http_task_results`',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

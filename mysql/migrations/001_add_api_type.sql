-- Migration: Add api_type column to tasks table
-- Date: 2025-11-03
-- Description: Add api_type field to support different API types (openai-chat, claude-chat, embeddings, custom-chat)

USE lmeterx;

-- Check if column exists before adding
SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'lmeterx'
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'api_type'
);

-- Add api_type column if it doesn't exist
SET @sql = IF(@column_exists = 0,
    'ALTER TABLE `tasks` ADD COLUMN `api_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT ''openai-chat'' COMMENT ''API type: openai-chat, claude-chat, embeddings, custom-chat'' AFTER `field_mapping`',
    'SELECT ''Column api_type already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Also ensure field_mapping is using longtext instead of json for consistency
-- (This is safe as the model uses Text type)
SET @field_mapping_type = (
    SELECT DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'lmeterx'
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'field_mapping'
);

SET @sql2 = IF(@field_mapping_type = 'json',
    'ALTER TABLE `tasks` MODIFY COLUMN `field_mapping` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT ''Field mapping configuration for custom APIs (JSON string)''',
    'SELECT ''Column field_mapping type is correct'' AS message'
);

PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

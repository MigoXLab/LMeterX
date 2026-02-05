-- Add warmup configuration fields to tasks table
ALTER TABLE `tasks`
ADD COLUMN `warmup_enabled` tinyint(1) DEFAULT '1' COMMENT 'Warmup mode: 0=disabled, 1=enabled' AFTER `chat_type`,
ADD COLUMN `warmup_duration` int(11) DEFAULT '120' COMMENT 'Warmup duration in seconds (10-1800)' AFTER `warmup_enabled`;

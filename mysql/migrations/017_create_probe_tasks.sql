-- Migration 017: Create probe_tasks table for lightweight engine connectivity tests

CREATE TABLE IF NOT EXISTS `probe_tasks` (
    `id` VARCHAR(36) NOT NULL,
    `cluster_id` VARCHAR(64) NOT NULL,
    `probe_type` VARCHAR(10) NOT NULL COMMENT '"llm" | "http"',
    `status` VARCHAR(16) NOT NULL DEFAULT 'pending',
    `engine_id` VARCHAR(64) DEFAULT NULL,
    `request_config` JSON NOT NULL,
    `result` JSON DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `completed_at` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_probe_cluster_status` (`cluster_id`, `status`),
    KEY `idx_probe_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Unified FIFO dispatch queue for LLM and HTTP tasks.
-- Historical terminal tasks are intentionally not copied. Only active tasks
-- that still need dispatch receive lightweight queue references.

CREATE TABLE IF NOT EXISTS `task_dispatch_queue` (
  `queue_seq` bigint NOT NULL AUTO_INCREMENT,
  `task_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `task_id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cluster_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'local',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'created',
  `engine_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `claimed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`queue_seq`),
  UNIQUE KEY `uk_dispatch_task` (`task_type`, `task_id`),
  KEY `idx_dispatch_cluster_status_seq` (`cluster_id`, `status`, `queue_seq`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `task_dispatch_queue`
  (`task_type`, `task_id`, `cluster_id`, `status`, `created_at`)
SELECT
  pending.`task_type`,
  pending.`task_id`,
  pending.`cluster_id`,
  pending.`queue_status`,
  pending.`created_at`
FROM (
  SELECT
    'llm' AS `task_type`,
    `id` AS `task_id`,
    COALESCE(`cluster_id`, 'local') AS `cluster_id`,
    IF(`status` = 'created', 'created', 'queued') AS `queue_status`,
    `created_at`
  FROM `llm_tasks`
  WHERE `status` IN ('created', 'queuing') AND `is_deleted` = 0

  UNION ALL

  SELECT
    'http' AS `task_type`,
    `id` AS `task_id`,
    COALESCE(`cluster_id`, 'local') AS `cluster_id`,
    IF(`status` = 'created', 'created', 'queued') AS `queue_status`,
    `created_at`
  FROM `http_tasks`
  WHERE `status` IN ('created', 'queuing') AND `is_deleted` = 0
) AS pending
ORDER BY pending.`created_at`, pending.`task_type`, pending.`task_id`;

-- Add standards-based A2A and MCP load-test task/result tables.

CREATE TABLE IF NOT EXISTS `agent_tasks` (
  `id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `protocol` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `protocol_version` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_url` varchar(2000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_host` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `api_path` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL,
  `headers` json DEFAULT NULL,
  `protocol_config` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `concurrent_users` int(11) NOT NULL,
  `spawn_rate` int(11) NOT NULL,
  `duration` int(11) NOT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `engine_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cluster_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'local',
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_agent_status_created` (`status`,`created_at`),
  KEY `idx_agent_protocol_created` (`protocol`,`created_at`),
  KEY `idx_agent_cluster_status` (`cluster_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `agent_task_results` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_type` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `num_requests` int(11) NOT NULL DEFAULT '0',
  `num_failures` int(11) NOT NULL DEFAULT '0',
  `avg_latency` float NOT NULL DEFAULT '0',
  `min_latency` float NOT NULL DEFAULT '0',
  `max_latency` float NOT NULL DEFAULT '0',
  `median_latency` float NOT NULL DEFAULT '0',
  `p95_latency` float NOT NULL DEFAULT '0',
  `rps` float NOT NULL DEFAULT '0',
  `avg_content_length` float NOT NULL DEFAULT '0',
  `metric_data` longtext COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_agent_results_task_metric` (`task_id`,`metric_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

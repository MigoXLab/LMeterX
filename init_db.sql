SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS lmeterx;
USE lmeterx;

-- ----------------------------
-- Table structure for tasks
-- ----------------------------
DROP TABLE IF EXISTS `tasks`;
CREATE TABLE `tasks` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'idle',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Creator username',
  `target_host` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `api_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '/chat/completions' COMMENT 'API path',
  `request_payload` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Custom request payload for non-chat completions APIs',
  `field_mapping` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Field mapping configuration for custom APIs (JSON string)',
  `api_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'openai-chat' COMMENT 'API type: openai-chat, claude-chat, embeddings, custom-chat',
  `model` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `test_data` longtext COLLATE utf8mb4_unicode_ci,
  `stream_mode` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'True',
  `concurrent_users` int(11) DEFAULT '1',
  `spawn_rate` int(11) DEFAULT '0',
  `duration` int(11) DEFAULT '60',
  `chat_type` int(11) DEFAULT '0',
  `warmup_enabled` tinyint(1) DEFAULT '1' COMMENT 'Warmup mode: 0=disabled, 1=enabled',
  `warmup_duration` int(11) DEFAULT '120' COMMENT 'Warmup duration in seconds (10-1800)',
  `log_file` longtext COLLATE utf8mb4_unicode_ci,
  `result_file` longtext COLLATE utf8mb4_unicode_ci,
  `cert_file` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `key_file` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `headers` json DEFAULT NULL,
  `cookies` json DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete flag: 0=active, 1=deleted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_status_created` (`status`,`created_at`),
  KEY `idx_created_by` (`created_by`),
  KEY `idx_name` (`name`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_model` (`model`),
  KEY `idx_model_concurrent_status` (`model`, `concurrent_users`, `status`, `created_at`),
  KEY `idx_is_deleted` (`is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for task_results
-- ----------------------------
DROP TABLE IF EXISTS `task_results`;
CREATE TABLE `task_results` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'task id',
  `metric_type` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'metric type',
  `num_requests` int(11) DEFAULT '0' COMMENT 'request total',
  `num_failures` int(11) DEFAULT '0' COMMENT 'request failure total',
  `avg_latency` float DEFAULT '0' COMMENT 'request average response time',
  `min_latency` float DEFAULT '0' COMMENT 'request minimum response time',
  `max_latency` float DEFAULT '0' COMMENT 'request maximum response time',
  `median_latency` float DEFAULT '0' COMMENT 'request median response time',
  `p90_latency` float DEFAULT '0' COMMENT 'request 90% response time',
  `rps` float DEFAULT '0' COMMENT 'request per second',
  `avg_content_length` float DEFAULT '0' COMMENT 'average output character length',
  `completion_tps` float DEFAULT '0' COMMENT 'completion tokens per second',
  `total_tps` float DEFAULT '0' COMMENT 'total tokens per second',
  `avg_total_tokens_per_req` float DEFAULT '0' COMMENT 'average total tokens per request',
  `avg_completion_tokens_per_req` float DEFAULT '0' COMMENT 'average completion tokens per request',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
  PRIMARY KEY (`id`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_task_metric_created` (`task_id`, `metric_type`, `created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=262 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for common_tasks
-- ----------------------------
DROP TABLE IF EXISTS `common_tasks`;
CREATE TABLE `common_tasks` (
  `id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Creator username',
  `method` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_url` varchar(2000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_host` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `api_path` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL,
  `headers` json DEFAULT NULL,
  `cookies` json DEFAULT NULL,
  `request_body` longtext COLLATE utf8mb4_unicode_ci,
  `dataset_file` longtext COLLATE utf8mb4_unicode_ci,
  `curl_command` longtext COLLATE utf8mb4_unicode_ci,
  `concurrent_users` int(11) NOT NULL,
  `spawn_rate` int(11) NOT NULL,
  `duration` int(11) NOT NULL,
  `log_file` longtext COLLATE utf8mb4_unicode_ci,
  `result_file` longtext COLLATE utf8mb4_unicode_ci,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Soft delete flag: 0=active, 1=deleted',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_common_status_created` (`status`,`created_at`),
  KEY `idx_common_created_by` (`created_by`),
  KEY `idx_common_name` (`name`),
  KEY `idx_common_created` (`created_at`),
  KEY `idx_is_deleted` (`is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for common_task_results
-- ----------------------------
DROP TABLE IF EXISTS `common_task_results`;
CREATE TABLE `common_task_results` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'task id',
  `metric_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `num_requests` int(11) NOT NULL DEFAULT '0',
  `num_failures` int(11) NOT NULL DEFAULT '0',
  `avg_latency` float NOT NULL DEFAULT '0',
  `min_latency` float NOT NULL DEFAULT '0',
  `max_latency` float NOT NULL DEFAULT '0',
  `median_latency` float NOT NULL DEFAULT '0',
  `p90_latency` float NOT NULL DEFAULT '0',
  `rps` float NOT NULL DEFAULT '0',
  `avg_content_length` float NOT NULL DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
  PRIMARY KEY (`id`),
  KEY `idx_common_task_id` (`task_id`),
  KEY `idx_common_task_metric_created` (`task_id`, `metric_type`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for test_insights
-- ----------------------------
DROP TABLE IF EXISTS `test_insights`;
CREATE TABLE `test_insights` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'task id',
  `eval_prompt` longtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'AI analysis prompt',
  `analysis_report` longtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'AI analysis content',
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'completed' COMMENT 'analysis status',
  `error_message` text COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'error message if analysis failed',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_id` (`task_id`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for system_config
-- ----------------------------
DROP TABLE IF EXISTS `system_config`;
CREATE TABLE `system_config` (
  `id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'config id',
  `config_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'config key',
  `config_value` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'config value',
  `description` text COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'config description',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'updated time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`),
  KEY `idx_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

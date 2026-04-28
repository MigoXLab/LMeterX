-- ----------------------------
-- Table structure for collections
-- ----------------------------
DROP TABLE IF EXISTS `collections`;
CREATE TABLE `collections` (
  `id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `rich_content` longtext COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Rich text and chart config',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Creator username',
  `is_public` tinyint(1) NOT NULL DEFAULT '1' COMMENT '0=private, 1=public',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_created_by` (`created_by`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Table structure for collection_tasks
-- ----------------------------
DROP TABLE IF EXISTS `collection_tasks`;
CREATE TABLE `collection_tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `collection_id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `task_id` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `task_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'http or llm',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_collection_task` (`collection_id`, `task_id`),
  KEY `idx_collection_id` (`collection_id`),
  KEY `idx_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

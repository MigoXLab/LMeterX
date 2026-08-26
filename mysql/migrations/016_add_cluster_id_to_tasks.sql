-- Migration 016: Add cluster_id to task tables for cluster-aware task routing

ALTER TABLE llm_tasks
    ADD COLUMN cluster_id VARCHAR(64) DEFAULT NULL AFTER engine_id,
    ADD INDEX idx_cluster_status (cluster_id, status);

ALTER TABLE http_tasks
    ADD COLUMN cluster_id VARCHAR(64) DEFAULT NULL AFTER engine_id,
    ADD INDEX idx_cluster_status (cluster_id, status);

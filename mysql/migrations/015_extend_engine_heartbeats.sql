-- Migration 015: Extend engine_heartbeats for multi-cluster support
-- Adds cluster_id, resource metrics, and status tracking fields.

ALTER TABLE engine_heartbeats
    ADD COLUMN cluster_id VARCHAR(64) NOT NULL DEFAULT 'local' AFTER engine_id,
    ADD COLUMN status ENUM('online', 'busy', 'offline') NOT NULL DEFAULT 'online' AFTER cluster_id,
    ADD COLUMN running_tasks JSON DEFAULT NULL,
    ADD COLUMN cpu_usage FLOAT NOT NULL DEFAULT 0,
    ADD COLUMN memory_usage FLOAT NOT NULL DEFAULT 0,
    ADD COLUMN available_slots INT NOT NULL DEFAULT 1,
    ADD COLUMN version VARCHAR(32) DEFAULT NULL,
    ADD COLUMN registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD INDEX idx_cluster_status (cluster_id, status);

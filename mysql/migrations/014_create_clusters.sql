-- Migration 014: Create clusters table for multi-cluster engine management
-- This table stores cluster metadata for distributed engine deployment.

CREATE TABLE IF NOT EXISTS clusters (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    status ENUM('active', 'inactive', 'draining') NOT NULL DEFAULT 'active',
    desired_replicas INT NOT NULL DEFAULT 1,
    min_replicas INT NOT NULL DEFAULT 1,
    max_replicas INT NOT NULL DEFAULT 10,
    current_replicas INT NOT NULL DEFAULT 0,
    ready_replicas INT NOT NULL DEFAULT 0,
    api_token VARCHAR(128) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert a default 'local' cluster for docker-compose compatibility
INSERT IGNORE INTO clusters (id, name, description, status, desired_replicas)
VALUES ('local', 'Local', 'Default local cluster for local deployment', 'active', 1);

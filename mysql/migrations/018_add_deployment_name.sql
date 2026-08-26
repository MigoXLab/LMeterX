-- Migration 018: Add deployment_name and pod_name to engine_heartbeats
-- Enables deployment-level filtering to prevent unauthorized engines from registering.

ALTER TABLE engine_heartbeats
    ADD COLUMN deployment_name VARCHAR(128) DEFAULT NULL AFTER engine_id,
    ADD COLUMN pod_name VARCHAR(253) DEFAULT NULL AFTER deployment_name;

-- Add success_assert column to http_tasks table
-- This field stores user-defined business-level success assertion rules as JSON.
-- When set, the load test engine will check the response body against this rule
-- and mark requests as failures if the assertion does not match, even if HTTP status is 200.
--
-- Example JSON:
--   {"field": "code", "operator": "eq", "value": 0}
--   {"field": "status", "operator": "in", "value": ["ok", "success"]}

ALTER TABLE `http_tasks` ADD COLUMN `success_assert` text DEFAULT NULL COMMENT 'Business-level success assertion rule (JSON)' AFTER `curl_command`;

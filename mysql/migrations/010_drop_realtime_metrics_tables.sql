-- Migration 010: Drop realtime metrics tables
-- Real-time performance metrics are now stored in VictoriaMetrics.
-- These MySQL tables are no longer written to or read from.

DROP TABLE IF EXISTS `task_realtime_metrics`;
DROP TABLE IF EXISTS `common_task_realtime_metrics`;

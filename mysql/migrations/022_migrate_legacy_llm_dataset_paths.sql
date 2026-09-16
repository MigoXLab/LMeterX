-- Migration 022: Replace legacy built-in LLM dataset markers with file paths.
--
-- Historical LLM tasks stored `test_data = 'default'` and selected the actual
-- built-in dataset through `chat_type`. Convert every such row before removing
-- the compatibility column in migration 023. Unknown values retain the old
-- fallback behavior and use the self-built text dataset.

UPDATE `llm_tasks`
SET `test_data` = CASE `chat_type`
  WHEN 0 THEN '/app/upload_files/xxx/text_self-built.jsonl'
  WHEN 1 THEN '/app/upload_files/xxx/ShareGPT_V3_partial.jsonl'
  WHEN 2 THEN '/app/upload_files/xxx/comprehensive_self-build.jsonl'
  ELSE '/app/upload_files/xxx/text_self-built.jsonl'
END
WHERE LOWER(TRIM(COALESCE(`test_data`, ''))) = 'default';

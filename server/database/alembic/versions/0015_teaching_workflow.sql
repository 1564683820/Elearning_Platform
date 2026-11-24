-- Additive upgrade for installations that already applied 0014_teaching_tasks.sql.
-- Apply only to an explicitly selected development database after backup.
ALTER TABLE teaching_task
  ADD COLUMN artifact JSON NULL,
  ADD COLUMN artifact_version INT NOT NULL DEFAULT 0,
  ADD COLUMN approved_version INT NULL,
  ADD COLUMN published_exam_id BIGINT NULL,
  ADD COLUMN error_code VARCHAR(64) NULL,
  ADD COLUMN lease_owner VARCHAR(64) NULL,
  ADD COLUMN lease_until DATETIME NULL,
  ADD COLUMN attempts INT NOT NULL DEFAULT 0,
  ADD UNIQUE KEY uk_teaching_task_exam (published_exam_id);
UPDATE teaching_task SET artifact = JSON_OBJECT() WHERE artifact IS NULL;
ALTER TABLE teaching_task MODIFY artifact JSON NOT NULL;
CREATE TABLE teaching_task_outbox (
  id BIGINT PRIMARY KEY, task_id BIGINT NOT NULL,
  delivered_at DATETIME NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_teaching_outbox_task (task_id)
) CHARACTER SET utf8mb4;

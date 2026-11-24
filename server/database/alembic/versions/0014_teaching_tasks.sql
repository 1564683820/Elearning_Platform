-- Additive schema for teaching workflows. Confirm target before running.
CREATE TABLE teaching_task (
    id BIGINT NOT NULL PRIMARY KEY,
    teacher_id BIGINT NOT NULL,
    class_id BIGINT NOT NULL,
    objective TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'created',
    checkpoint JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_teaching_task_owner (teacher_id, created_at)
) CHARACTER SET utf8mb4;

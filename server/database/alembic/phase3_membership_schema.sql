-- ==========================================================
-- Phase 3 — 会员体系
-- 表: user_membership_order, redeem_code
-- ==========================================================

-- 会员订单表
CREATE TABLE IF NOT EXISTS user_membership_order (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
  plan VARCHAR(32) NOT NULL COMMENT '套餐: vip_student/vip_teacher/vip_teacher_pro',
  order_no VARCHAR(64) NOT NULL UNIQUE COMMENT '商户订单号',
  amount DECIMAL(8,2) NOT NULL COMMENT '支付金额(元)',
  duration_months INT NOT NULL COMMENT '时长(月)',
  payment_status ENUM('pending','paid','refunded','cancelled') DEFAULT 'pending' COMMENT '支付状态',
  pay_type ENUM('wxpay','redeem') DEFAULT 'wxpay' COMMENT '支付方式',
  paid_at DATETIME DEFAULT NULL COMMENT '支付时间',
  expire_at DATETIME DEFAULT NULL COMMENT '会员到期时间',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY idx_user (user_id),
  KEY idx_order_no (order_no),
  KEY idx_payment_status (payment_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员订单表';

-- 兑换码主表
CREATE TABLE IF NOT EXISTS redeem_code (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE COMMENT '兑换码',
  plan VARCHAR(32) NOT NULL COMMENT '对应套餐: vip_student/vip_teacher/vip_teacher_pro',
  duration_months INT NOT NULL DEFAULT 1 COMMENT '时长(月)',
  status ENUM('active','used','expired','disabled') DEFAULT 'active' COMMENT '状态',
  created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人(管理员ID)',
  batch_no VARCHAR(64) DEFAULT NULL COMMENT '批次号',
  used_by BIGINT UNSIGNED DEFAULT NULL COMMENT '使用者ID',
  used_at DATETIME DEFAULT NULL COMMENT '使用时间',
  expire_at DATETIME DEFAULT NULL COMMENT '兑换码过期时间(NULL=永不)',
  remark VARCHAR(256) DEFAULT '' COMMENT '备注',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY idx_status (status),
  KEY idx_used_by (used_by),
  KEY idx_batch_no (batch_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='兑换码表';

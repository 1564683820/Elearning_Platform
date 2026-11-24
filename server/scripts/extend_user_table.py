# 用户表扩展迁移脚本
# 为 User 表添加 role、membership、membership_expire 字段
# 用法: python -m scripts.extend_user_table
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import engine
from app.core.config import get_settings


async def extend_user_table():
    """执行 User 表字段扩展迁移"""
    settings = get_settings()
    print(f"📦 连接数据库: {settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}")

    async with engine.begin() as conn:
        # role 字段
        await conn.exec_driver_sql(
            "ALTER TABLE `user` "
            "ADD COLUMN `role` VARCHAR(16) NOT NULL DEFAULT 'student' "
            "COMMENT '角色: student/teacher/personal/admin' "
            "AFTER `nickname`"
        )
        print("✅ role 字段添加成功")

        # membership 字段
        await conn.exec_driver_sql(
            "ALTER TABLE `user` "
            "ADD COLUMN `membership` VARCHAR(32) NOT NULL DEFAULT 'free' "
            "COMMENT '会员等级: free/basic/premium/pro' "
            "AFTER `role`"
        )
        print("✅ membership 字段添加成功")

        # membership_expire 字段
        await conn.exec_driver_sql(
            "ALTER TABLE `user` "
            "ADD COLUMN `membership_expire` DATETIME DEFAULT NULL "
            "COMMENT '会员到期时间' "
            "AFTER `membership`"
        )
        print("✅ membership_expire 字段添加成功")

    print("🎉 用户表扩展迁移完成")


async def main():
    try:
        await extend_user_table()
    except Exception as e:
        error_msg = str(e)
        if "Duplicate column" in error_msg:
            print("⚠️  部分字段已存在，跳过重复添加")
        else:
            print(f"❌ 迁移失败: {error_msg}")
            raise


if __name__ == "__main__":
    asyncio.run(main())

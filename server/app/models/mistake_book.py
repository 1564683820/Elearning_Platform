"""
错题本 Model — 存储小e总结的错题报告
"""
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func
from app.db.database import Base
from app.utils.snowflake import next_id


class MistakeSummaryReport(Base):
    """错题总结报告表：小e生成的错题总结报告，保存在小e总结类"""
    __tablename__ = "mistake_summary_report"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    title = Column(String(256), default="", comment="报告标题")
    content = Column(Text, nullable=False, comment="报告内容(Markdown)")
    exam_name = Column(String(256), default="", comment="关联考试名称")
    days = Column(Integer, default=0, comment="覆盖天数(0=全部)")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "错题总结报告表"},
    )

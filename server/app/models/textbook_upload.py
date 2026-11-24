"""
教材上传记录 Model — 追踪用户上传的 PDF 教材文件及解析状态

表:
  textbook_upload  教材文件上传记录表
"""
from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class TextbookUpload(Base):
    """教材上传记录"""
    __tablename__ = "textbook_upload"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="上传用户ID")
    filename = Column(String(256), nullable=False, comment="原始文件名")
    file_key = Column(String(256), nullable=False, comment="存储路径（相对 uploads/）")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")

    # 教材元信息
    textbook_version = Column(String(64), default="", comment="教材版本 e.g. PEP")
    grade = Column(String(16), default="", comment="年级 e.g. 3,4,5,6")
    semester = Column(String(8), default="", comment="学期: 上/下")

    # 解析状态
    parse_status = Column(Integer, default=0, comment="解析状态: 0=待处理,1=解析中,2=已完成,3=失败")
    total_pages = Column(Integer, default=0, comment="PDF总页数")
    parsed_pages = Column(Integer, default=0, comment="已解析页数")
    error_msg = Column(String(512), default="", comment="错误信息")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "教材上传记录表"},
    )

from sqlalchemy import or_

from app.models.stats import UserDocument


EXAM_SOURCE = "exam_source"
CHAT_ATTACHMENT = "chat_attachment"
PRIVATE_DOCUMENT_CATEGORIES = (EXAM_SOURCE, CHAT_ATTACHMENT)


def library_documents():
    return or_(UserDocument.doc_category.is_(None), UserDocument.doc_category.not_in(PRIVATE_DOCUMENT_CATEGORIES))

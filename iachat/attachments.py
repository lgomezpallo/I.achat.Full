"""Bounded local extraction of user-provided documents. No external network calls."""
import base64
import binascii
import io
from pathlib import PurePath

MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_CHARS = 18_000

class AttachmentError(ValueError):
    pass

def extract(attachments):
    remaining = MAX_TOTAL_CHARS
    sections = []
    names = []
    if len(attachments) > 3:
        raise AttachmentError("too_many_attachments")
    for item in attachments:
        name = PurePath(item.name.replace("\\", "/")).name[:180]
        ext = name.lower().rsplit(".", 1)[-1]
        if ext not in ("txt", "md", "pdf"):
            raise AttachmentError("unsupported_attachment_type")
        if len(item.content_base64) > 3_000_000:
            raise AttachmentError("attachment_too_large")
        try:
            raw = base64.b64decode(item.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise AttachmentError("invalid_attachment_encoding")
        if len(raw) > MAX_FILE_BYTES:
            raise AttachmentError("attachment_too_large")
        if ext == "pdf":
            try:
                from pypdf import PdfReader
                pdf = PdfReader(io.BytesIO(raw), strict=False)
                if len(pdf.pages) > 40:
                    raise AttachmentError("pdf_too_many_pages")
                content = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except AttachmentError:
                raise
            except Exception:
                raise AttachmentError("pdf_text_unreadable")
        else:
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise AttachmentError("text_file_not_utf8")
        content = content.strip()
        if not content:
            raise AttachmentError("attachment_contains_no_text")
        names.append(name)
        sections.append("[DOCUMENTO: " + name + "]\n" + content[:remaining] + "\n[/DOCUMENTO]")
        remaining -= min(remaining, len(content))
        if remaining <= 0:
            break
    return "\n\n".join(sections), names

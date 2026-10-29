"""Versioned local evidence; hash checks detect corruption, not authenticity."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from .metrics import VERSION


def encoded(payload):
    return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def write_evidence(path,payload):
    document={'schema_version':VERSION,'formula_version':VERSION,'payload':payload,
              'sha256':hashlib.sha256(encoded(payload)).hexdigest(),
              'saved_at':datetime.now(timezone.utc).isoformat()}
    save_json(path,document)
    return document


def save_json(path,document):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(encoded(document));temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_evidence(path,platform,store):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('schema_version')!=VERSION or doc.get('formula_version')!=VERSION:
        raise ValueError('证据或公式版本不兼容。')
    payload=doc['payload']
    if hashlib.sha256(encoded(payload)).hexdigest()!=doc.get('sha256'):
        raise ValueError('证据哈希不符，禁止重放。')
    if payload.get('platform')!=platform or payload.get('store_key')!=store:
        raise ValueError('证据店铺或平台不符。')
    return payload

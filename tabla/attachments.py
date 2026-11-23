"""Managed, content-addressed document copies and portable backup payloads."""
from __future__ import annotations
import base64
import hashlib
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

EXTENSIONS = {'.pdf', '.txt', '.md', '.markdown', '.csv', '.json', '.log', '.rtf', '.docx',
              '.xlsx', '.pptx', '.png', '.jpg', '.jpeg', '.webp', '.gif'}
FILE_LIMIT = 25 * 1024 * 1024
TOTAL_LIMIT = 100 * 1024 * 1024
KEY = re.compile(r'^[a-f0-9]{64}\.[a-z0-9]{1,12}$')
FILE_FILTER = 'Documents (*.pdf *.txt *.md *.markdown *.csv *.json *.log *.rtf *.docx *.xlsx *.pptx);;Images (*.png *.jpg *.jpeg *.webp *.gif)'


def validate_metadata(items):
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError('Invalid attachment list (maximum 100 files per note).')
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('key'), str) or not KEY.fullmatch(item['key']):
            raise ValueError('Invalid attachment storage key.')
        name = item.get('name')
        if not isinstance(name, str) or not name or len(name) > 512 or any(c in name for c in ('/', '\\', '\x00', ':')):
            raise ValueError('Invalid attachment filename.')
        if Path(name).suffix.lower() not in EXTENSIONS or Path(item['key']).suffix.lower() not in EXTENSIONS:
            raise ValueError('Unsupported attachment type.')
        if type(item.get('size')) is not int or not 0 <= item['size'] <= FILE_LIMIT:
            raise ValueError('Invalid attachment size.')


class AttachmentVault:
    def __init__(self, directory):
        self.directory = Path(directory)

    def import_files(self, paths):
        paths = [Path(p) for p in paths]
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                raise ValueError('Choose a supported document or image file.')
            if path.stat().st_size > FILE_LIMIT:
                raise ValueError(f'{path.name} exceeds the 25 MB attachment limit.')
        if sum(path.stat().st_size for path in paths) > TOTAL_LIMIT or len(paths) > 100:
            raise ValueError('Import at most 100 MB or 100 files at a time.')
        self.directory.mkdir(parents=True, exist_ok=True)
        result = []
        for path in paths:
            data = path.read_bytes()
            if len(data) > FILE_LIMIT:
                raise ValueError('The file grew beyond the attachment size limit.')
            digest = hashlib.sha256(data).hexdigest()
            key = digest + path.suffix.lower()
            target = self.directory / key
            self.write_blob(key, data)
            result.append({'id': str(uuid.uuid4()), 'key': key, 'name': path.name,
                           'size': len(data), 'mime': mimetypes.guess_type(path.name)[0] or 'application/octet-stream'})
        return result

    def path_for(self, item):
        validate_metadata([item])
        root = self.directory.resolve()
        path = (root / item['key']).resolve()
        if path.parent != root:
            raise ValueError('Attachment path is outside the workspace.')
        return path

    def write_blob(self, key, data):
        if not KEY.fullmatch(key) or hashlib.sha256(data).hexdigest() != key[:64]:
            raise ValueError('Attachment content does not match its storage key.')
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / key
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == key[:64]:
            return
        temporary = self.directory / ('.import-' + uuid.uuid4().hex)
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def pack(self, records):
        files, total = {}, 0
        for record in records:
            validate_metadata(record.get('attachments', []))
            for item in record.get('attachments', []):
                if item['key'] in files:
                    continue
                path = self.path_for(item)
                if not path.is_file():
                    raise ValueError(f'Attachment missing: {item["name"]}. Restore its file before exporting.')
                data = path.read_bytes()
                if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['key'][:64]:
                    raise ValueError('Attachment contents changed unexpectedly.')
                total += len(data)
                if total > TOTAL_LIMIT:
                    raise ValueError('This export exceeds the 100 MB total attachment limit.')
                files[item['key']] = {'key': item['key'], 'data': base64.b64encode(data).decode('ascii')}
        return list(files.values())

    def validate_bundle(self, files, records):
        if not isinstance(files, list) or len(files) > 10000:
            raise ValueError('Invalid attachment bundle.')
        decoded, total = {}, 0
        for blob in files:
            if not isinstance(blob, dict) or not isinstance(blob.get('key'), str) or not KEY.fullmatch(blob['key']) or Path(blob['key']).suffix.lower() not in EXTENSIONS:
                raise ValueError('Invalid bundled attachment key.')
            if blob['key'] in decoded or not isinstance(blob.get('data'), str) or len(blob['data']) > FILE_LIMIT * 1.34 + 8:
                raise ValueError('Invalid bundled attachment data.')
            try:
                data = base64.b64decode(blob['data'], validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError('Invalid attachment encoding.') from exc
            total += len(data)
            if len(data) > FILE_LIMIT or total > TOTAL_LIMIT or hashlib.sha256(data).hexdigest() != blob['key'][:64]:
                raise ValueError('Attachment size or checksum failed validation.')
            decoded[blob['key']] = data
        for record in records:
            validate_metadata(record.get('attachments', []))
            for item in record.get('attachments', []):
                data = decoded.get(item['key'])
                if data is None:
                    path = self.path_for(item)
                    if not path.is_file():
                        raise ValueError('The backup is missing an attachment: ' + item['name'])
                    data = path.read_bytes()
                if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['key'][:64]:
                    raise ValueError('Attachment metadata does not match its contents.')
        return decoded


def short_name(name, length=32):
    if len(name) <= length:
        return name
    suffix = Path(name).suffix
    budget = max(8, length - len(suffix) - 1)
    stem = name[:-len(suffix)] if suffix else name
    return stem[:budget // 2] + '…' + stem[-(budget - budget // 2):] + suffix

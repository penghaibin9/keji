"""Bounded PDF parsing and ordinary scanned-document compatibility."""
from io import BytesIO
import zlib

import pytest
from fastapi import HTTPException
from PIL import Image
from pypdf import apply_configuration
from app.routes.files import inspect_upload


def compressed_xref_pdf(filters=b'/FlateDecode'):
    data = bytearray(b'%PDF-1.5\n')
    offsets = [0]
    for number, body in enumerate([
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>',
    ], 1):
        offsets.append(len(data))
        data.extend(str(number).encode() + b' 0 obj\n' + body + b'\nendobj\n')
    offsets.append(len(data))
    xref = b'\x00\x00\x00\x00\x00\xff\xff' + b''.join(
        b'\x01' + offset.to_bytes(4, 'big') + b'\x00\x00' for offset in offsets[1:]
    )
    encoded = zlib.compress(xref)
    if filters.startswith(b'['):
        encoded = zlib.compress(encoded)
    data.extend(
        b'4 0 obj\n<< /Type /XRef /Size 5 /Root 1 0 R /W [1 4 2] /Filter '
        + filters + b' /Length ' + str(len(encoded)).encode()
        + b' >>\nstream\n' + encoded + b'\nendstream\nendobj\nstartxref\n'
        + str(offsets[4]).encode() + b'\n%%EOF\n'
    )
    return bytes(data)


@pytest.mark.parametrize('filters', [b'/FlateDecode', b'[/FlateDecode /FlateDecode]'])
def test_compressed_xref_respects_bounded_decompression(filters):
    data = compressed_xref_pdf(filters)
    assert len(data) < 512
    assert inspect_upload('xref.pdf', data) == 'application/pdf'
    # The decoded xref is only 35 bytes; a tiny limit exercises rejection safely.
    with apply_configuration(zlib_maximum_output_length=16):
        with pytest.raises(HTTPException) as exc:
            inspect_upload('xref.pdf', data)
        assert exc.value.status_code == 422
    assert inspect_upload('xref.pdf', data) == 'application/pdf'


def test_scanned_pdf_is_accepted():
    stream = BytesIO()
    Image.new('RGB', (8, 8), 'white').save(stream, format='PDF')
    assert inspect_upload('扫描证明.pdf', stream.getvalue()) == 'application/pdf'

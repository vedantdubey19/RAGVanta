"""Run inside the lean Linux image: hosted API and resource-limited PDF smoke verification."""
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.auth import CSRF_COOKIE
import pymupdf

assert os.geteuid() != 0
with tempfile.TemporaryDirectory() as directory:
    config = Settings(data_dir=Path(directory), deployment='hosted', public_url='https://test.example',
                      pdf_memory_mb=192, _env_file=None)
    with TestClient(create_app(config), base_url='https://test.example') as client:
        assert client.get('/health').status_code == 200
        assert client.get('/v1/collections').status_code == 401
        client.app.state.auth.create_user('operator', 'synthetic-container-password')
        assert client.post('/auth/login',json={'username':'operator','password':'synthetic-container-password'},
                           headers={'Origin':'https://test.example'}).status_code == 200
        headers={'Origin':'https://test.example','X-CSRF-Token':client.cookies.get(CSRF_COOKIE)}
        cid=client.post('/v1/collections',json={'name':'smoke'},headers=headers).json()['id']
        pdf=pymupdf.open()
        pdf.new_page().insert_text((72,72),'Returns are accepted within 14 days.')
        upload=client.post('/v1/documents',data={'collection_id':cid,'synthetic':'true'},
                           files={'file':('policy.pdf',pdf.tobytes())},headers=headers)
        pdf.close()
        assert upload.status_code==201,upload.text
        answer=client.post('/v1/chat',json={'collection_id':cid,'question':'What is the return window?'},headers=headers)
        assert answer.status_code==200,answer.text
        assert '14 days' in answer.json()['answer'] and answer.json()['citations'],answer.text
        assert client.get('/').headers.get('Content-Security-Policy')
        assert client.post('/auth/logout',headers=headers).status_code==204
        assert client.get('/v1/collections').status_code==401
print('Linux non-root container smoke passed: hosted auth, CSRF, PDF limits, cited Q&A, logout, headers')

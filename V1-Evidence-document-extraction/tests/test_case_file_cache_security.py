from __future__ import annotations

import socket

import pytest

from sl_legal_rag.db import repositories


def test_remote_document_url_rejects_private_ip_literal():
    with pytest.raises(ValueError, match="blocked network"):
        repositories._validate_remote_document_url("https://127.0.0.1/secret.pdf")


def test_remote_document_url_rejects_private_dns_resolution(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(repositories.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="blocked network"):
        repositories._validate_remote_document_url("https://example.test/document.pdf")


def test_remote_document_url_honours_allowlisted_hosts(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(repositories.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv(repositories.CASE_FILE_CACHE_ALLOWED_HOSTS_ENV, "parliament.lk,supremecourt.lk")

    repositories._validate_remote_document_url("https://www.parliament.lk/uploads/acts/example.pdf")
    with pytest.raises(ValueError, match="not allowlisted"):
        repositories._validate_remote_document_url("https://example.com/document.pdf")

"""Security and validation tests for product licensing."""

from datetime import datetime, timedelta

import pytest

from core.license import (
    create_license_key,
    generate_key_pair,
    serialize_private_key,
    serialize_public_key,
    validate_license_key,
)


def test_license_generation_requires_external_private_key():
    with pytest.raises(ValueError, match="chave privada"):
        create_license_key(
            customer="Cliente",
            email="cliente@example.com",
            expiry_date=datetime.now() + timedelta(days=30),
        )


def test_generated_license_validates_with_matching_public_key():
    private_key, public_key = generate_key_pair()
    token = create_license_key(
        customer="Cliente",
        email="cliente@example.com",
        expiry_date=datetime.now() + timedelta(days=30),
        private_key_pem=serialize_private_key(private_key).encode(),
    )

    valid, message, payload = validate_license_key(
        token,
        public_key_pem=serialize_public_key(public_key).encode(),
    )

    assert valid is True
    assert message == "Licenca valida."
    assert payload["customer"] == "Cliente"


def test_license_without_configured_public_key_is_rejected(monkeypatch):
    private_key, _public_key = generate_key_pair()
    token = create_license_key(
        customer="Cliente",
        email="cliente@example.com",
        expiry_date=datetime.now() + timedelta(days=30),
        private_key_pem=serialize_private_key(private_key).encode(),
    )
    monkeypatch.setattr("core.license._load_product_public_key", lambda: None)

    valid, message, _payload = validate_license_key(token)

    assert valid is False
    assert "nao configurado" in message

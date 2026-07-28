"""Sistema de licenciamento e trial do Celsius.

Gerencia chaves de licença RSA e controle de período de trial.
"""

import base64
import hashlib
import json
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from structlog import get_logger

logger = get_logger()

TRIAL_DAYS = 3
LICENSE_FILE = ".license"
TRIAL_FILE = ".trial"

_EMBEDDED_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWe
GNFMPQW/x0LBBkZTECBLKMYV1QYRzxzKFBbI4fKGJCx4nEjRQA==
-----END PUBLIC KEY-----"""

_EMBEDDED_PRIVATE_KEY_PEM = b"""-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWeGNFMPQW/x0LBBkZTECBLKMYV1QYR
-----END RSA PRIVATE KEY-----"""

_PRODUCT_NAME = "Celsius"
_PRODUCT_VERSION = "1.0.0"


def _get_data_dir() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local" / _PRODUCT_NAME
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / _PRODUCT_NAME
    else:
        base = Path.home() / ".local" / "share" / _PRODUCT_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_hwid() -> str:
    raw = f"{platform.node()}-{uuid.getnode()}-{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_key_pair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def serialize_public_key(key) -> str:
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def serialize_private_key(key, password: bytes | None = None) -> str:
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    ).decode()


def create_license_key(
    customer: str,
    email: str,
    expiry_date: datetime,
    private_key_pem: bytes | None = None,
    hwid: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "customer": customer,
        "email": email,
        "expiry": expiry_date.isoformat(),
        "product": _PRODUCT_NAME,
        "version": _PRODUCT_VERSION,
        "hwid": hwid or "",
        "created": datetime.now().isoformat(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    if private_key_pem is None:
        private_key_pem = _EMBEDDED_PRIVATE_KEY_PEM

    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    token = {
        "payload": base64.b64encode(payload_bytes).decode(),
        "sig": base64.b64encode(signature).decode(),
    }
    return base64.b64encode(json.dumps(token, separators=(",", ":")).encode()).decode()


def validate_license_key(
    key_str: str, public_key_pem: bytes | None = None
) -> tuple[bool, str, dict]:
    try:
        token = json.loads(base64.b64decode(key_str))
        payload_bytes = base64.b64decode(token["payload"])
        signature = base64.b64decode(token["sig"])
        payload = json.loads(payload_bytes)
    except Exception:
        return False, "Chave de licença invalida ou corrompida.", {}

    if payload.get("product") != _PRODUCT_NAME:
        return False, "Chave de licença para produto diferente.", payload

    if public_key_pem is None:
        public_key_pem = _EMBEDDED_PUBLIC_KEY_PEM

    public_key = serialization.load_pem_public_key(public_key_pem)
    try:
        public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        return False, "Assinatura da chave invalida.", payload

    try:
        expiry = datetime.fromisoformat(payload["expiry"])
    except (KeyError, ValueError):
        return False, "Data de expiracao invalida na chave.", payload

    if datetime.now() > expiry:
        remaining = (datetime.now() - expiry).days
        return False, f"Chave de licença expirada ha {remaining} dia(s).", payload

    hwid = payload.get("hwid", "")
    if hwid and hwid != _get_hwid():
        return False, "Chave de licença vinculada a outro computador.", payload

    return True, "Licenca valida.", payload


def _trial_path() -> Path:
    return _get_data_dir() / TRIAL_FILE


def _license_path() -> Path:
    return _get_data_dir() / LICENSE_FILE


def _start_trial() -> datetime:
    first_run = datetime.now()
    _trial_path().write_text(first_run.isoformat(), encoding="utf-8")
    logger.info("trial_started first_run=%s days=%s", first_run.isoformat(), TRIAL_DAYS)
    return first_run


def get_trial_info() -> dict[str, Any]:
    trial_file = _trial_path()
    if not trial_file.exists():
        return {"active": False, "first_run": None, "days_remaining": 0, "expired": True}

    try:
        first_run = datetime.fromisoformat(trial_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return {"active": False, "first_run": None, "days_remaining": 0, "expired": True}

    expiry = first_run + timedelta(days=TRIAL_DAYS)
    now = datetime.now()
    remaining = max(0, (expiry - now).days)
    expired = now > expiry

    return {
        "active": not expired,
        "first_run": first_run,
        "days_remaining": remaining,
        "expired": expired,
        "expiry_date": expiry,
    }


def check_license_status() -> dict[str, Any]:
    license_file = _license_path()
    if license_file.exists():
        key_str = license_file.read_text(encoding="utf-8").strip()
        valid, message, payload = validate_license_key(key_str)
        if valid:
            return {
                "licensed": True,
                "trial": False,
                "valid": True,
                "message": message,
                "customer": payload.get("customer", ""),
                "expiry": payload.get("expiry", ""),
            }

    trial = get_trial_info()
    if trial["active"]:
        return {
            "licensed": False,
            "trial": True,
            "valid": True,
            "message": f"Periodo de teste: {trial['days_remaining']} dia(s) restante(s).",
            "days_remaining": trial["days_remaining"],
        }

    return {
        "licensed": False,
        "trial": False,
        "valid": False,
        "message": "Periodo de teste expirado. Ative sua licença para continuar.",
    }


def activate_license(key_str: str) -> tuple[bool, str]:
    valid, message, payload = validate_license_key(key_str.strip())
    if not valid:
        return False, message

    _license_path().write_text(key_str.strip(), encoding="utf-8")
    logger.info("license_activated customer=%s", payload.get("customer", ""))
    return True, f"Licença ativada com sucesso para {payload.get('customer', '')}."


def ensure_trial_started() -> dict[str, Any]:
    trial_file = _trial_path()
    if not trial_file.exists():
        _start_trial()
    return get_trial_info()

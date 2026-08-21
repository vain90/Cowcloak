from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

PROTOCOL_VERSION = 1
SIGNATURE_HEADER = "X-Moolias-Signature"
TIMESTAMP_HEADER = "X-Moolias-Timestamp"
NONCE_HEADER = "X-Moolias-Nonce"

_MAILBOX_RE = re.compile(r"^[^\s@]+@[^\s@]+$")


class InvalidMailbox(ValueError):
    pass


def normalize_mailbox(value: str) -> str:
    mailbox = value.strip().casefold()
    if (
        not mailbox
        or len(mailbox) > 320
        or "\x00" in mailbox
        or "\r" in mailbox
        or "\n" in mailbox
        or not _MAILBOX_RE.fullmatch(mailbox)
    ):
        raise InvalidMailbox("Invalid mailbox address")

    local_part, domain = mailbox.rsplit("@", 1)
    if len(local_part) > 64 or len(domain) > 255 or not local_part or not domain:
        raise InvalidMailbox("Invalid mailbox address")
    return mailbox


def canonical_request(
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{body_hash}".encode()


def request_signature(
    secret: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        canonical_request(method, path, timestamp, nonce, body),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class AgentProtectionState:
    mailbox: str
    blocked: bool
    retry_after: int
    managed: bool = True

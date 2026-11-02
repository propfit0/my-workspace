"""암호화 데이터 저장소.

- 데이터는 SQLite(메모리)에서 처리하고, 변경이 확정(commit)될 때마다
  전체를 AES-256-GCM 으로 암호화하여 파일에 원자적으로 저장한다.
- 데이터 암호화 키(DEK)는 임의 생성되며 파일 머리말에 '감싸서' 보관한다.
  · v2(현재): Windows 계정(DPAPI)으로 감싼 키 → 비밀번호 없이 이 PC·이 계정에서 자동으로 열림
              + 복구 키로 감싼 키 → 다른 PC로 옮기거나 Windows를 다시 설치했을 때 사용
  · v1(이전 버전): 비밀번호로 감싼 키 + 복구 키. 읽기·전환만 지원한다.
- 저장 직전 파일은 .prev 로 한 단계 보관하여, 쓰기 도중 사고가 나도 직전 상태로 열 수 있다.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import secrets
import shutil
import sqlite3
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC1 = b"GJ01"
MAGIC2 = b"GJ02"
SALT_LEN = 16
WRAP_LEN = 12 + 32 + 16  # nonce + DEK + tag
HEADER1_LEN = 4 + SALT_LEN + WRAP_LEN + WRAP_LEN
SCRYPT_N = 2 ** 15
_DPAPI_ENTROPY = b"GounHaji-Consult-v2"


class WrongPassword(Exception):
    """비밀번호(또는 복구 키)가 올바르지 않음."""


class CorruptFile(Exception):
    """파일이 손상되었거나 형식이 올바르지 않음."""


class NeedMigration(Exception):
    """이전 버전(비밀번호 방식) 파일 — 한 번 전환이 필요함."""


class DeviceKeyUnavailable(Exception):
    """이 PC·이 Windows 계정으로는 자동으로 열 수 없음(복구 키 필요)."""


class SecretRequired(Exception):
    """파일을 열려면 복구 키(또는 예전 비밀번호)가 필요함."""


# ---- Windows DPAPI ----------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _mk_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(fn_name: str, data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    inb, _k1 = _mk_blob(data)
    ent, _k2 = _mk_blob(_DPAPI_ENTROPY)
    out = _Blob()
    fn = getattr(crypt32, fn_name)
    ok = fn(ctypes.byref(inb), None, ctypes.byref(ent), None, None, 1, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.GetLastError(), "DPAPI 호출 실패")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def dpapi_protect(data: bytes) -> bytes:
    return _dpapi("CryptProtectData", data)


def dpapi_unprotect(data: bytes) -> bytes:
    return _dpapi("CryptUnprotectData", data)


# ---- 키 도우미 --------------------------------------------------------------
def _kek_password(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


def normalize_recovery_key(text: str) -> bytes:
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum())
    try:
        return base64.b32decode(cleaned)
    except Exception as exc:  # noqa: BLE001
        raise WrongPassword("복구 키 형식이 올바르지 않습니다.") from exc


def _kek_recovery(text: str) -> bytes:
    return hashlib.sha256(b"GJ-recovery|" + normalize_recovery_key(text)).digest()


def new_recovery_key() -> str:
    raw = base64.b32encode(secrets.token_bytes(20)).decode("ascii")
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def _wrap(kek: bytes, dek: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(kek).encrypt(nonce, dek, None)


def _unwrap(kek: bytes, wrap: bytes, msg="비밀번호가 올바르지 않습니다.") -> bytes:
    try:
        return AESGCM(kek).decrypt(wrap[:12], wrap[12:], None)
    except InvalidTag as exc:
        raise WrongPassword(msg) from exc


# ---- 머리말 -----------------------------------------------------------------
@dataclass
class Parsed:
    version: int
    header_len: int
    rec_wrap: bytes
    salt: bytes = b""
    pw_wrap: bytes = b""
    dev_wrap: bytes = b""


def _parse(blob: bytes, need_body: bool = True) -> Parsed:
    bad = CorruptFile("데이터 파일 형식이 올바르지 않거나 손상되었습니다.")
    magic = blob[:4]
    if magic == MAGIC1:
        if len(blob) < HEADER1_LEN:
            raise bad
        p = Parsed(1, HEADER1_LEN, blob[4 + SALT_LEN + WRAP_LEN:HEADER1_LEN],
                   salt=blob[4:4 + SALT_LEN],
                   pw_wrap=blob[4 + SALT_LEN:4 + SALT_LEN + WRAP_LEN])
    elif magic == MAGIC2:
        if len(blob) < 4 + WRAP_LEN + 2:
            raise bad
        dlen = int.from_bytes(blob[4 + WRAP_LEN:6 + WRAP_LEN], "big")
        hl = 6 + WRAP_LEN + dlen
        if len(blob) < hl:
            raise bad
        p = Parsed(2, hl, blob[4:4 + WRAP_LEN], dev_wrap=blob[6 + WRAP_LEN:hl])
    else:
        raise bad
    if need_body and len(blob) < p.header_len + 12 + 16:
        raise bad
    return p


def _header_v1(salt, pw_wrap, rec_wrap) -> bytes:
    return MAGIC1 + salt + pw_wrap + rec_wrap


def _header_v2(rec_wrap: bytes, dev_wrap: bytes) -> bytes:
    return MAGIC2 + rec_wrap + len(dev_wrap).to_bytes(2, "big") + dev_wrap


def decrypt_blob(blob: bytes, password: str | None = None,
                 recovery_key: str | None = None, device: bool = False):
    """(dek, header, plaintext) 반환."""
    p = _parse(blob)
    if device:
        if p.version == 1:
            raise NeedMigration("이전 버전(비밀번호 방식) 데이터입니다.")
        try:
            dek = dpapi_unprotect(p.dev_wrap)
        except OSError as exc:
            raise DeviceKeyUnavailable("이 PC에서는 자동으로 열 수 없습니다.") from exc
        if len(dek) != 32:
            raise DeviceKeyUnavailable("이 PC에서는 자동으로 열 수 없습니다.")
    elif password is not None:
        if p.version != 1:
            raise WrongPassword("이 데이터 파일은 비밀번호를 사용하지 않습니다.")
        dek = _unwrap(_kek_password(password, p.salt), p.pw_wrap)
    elif recovery_key is not None:
        dek = _unwrap(_kek_recovery(recovery_key), p.rec_wrap, "복구 키가 올바르지 않습니다.")
    else:
        raise WrongPassword("열기 정보가 필요합니다.")
    header = blob[:p.header_len]
    nonce = blob[p.header_len:p.header_len + 12]
    try:
        plain = AESGCM(dek).decrypt(nonce, blob[p.header_len + 12:], header)
    except InvalidTag as exc:
        raise CorruptFile("데이터가 손상되었습니다.") from exc
    return dek, header, plain


def decrypt_any(blob: bytes, secret: str | None = None):
    """백업 파일 등을 열 때: 먼저 이 PC 자동 열기, 안 되면 복구 키(또는 예전 비밀번호)."""
    p = _parse(blob)
    if secret is None:
        if p.version == 2:
            try:
                return decrypt_blob(blob, device=True)
            except DeviceKeyUnavailable:
                pass
        raise SecretRequired()
    if p.version == 1:
        try:
            return decrypt_blob(blob, password=secret)
        except WrongPassword:
            pass
    return decrypt_blob(blob, recovery_key=secret)


class SecureStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.prev_path = self.path.with_suffix(self.path.suffix + ".prev")
        self.conn: sqlite3.Connection | None = None
        self._dek: bytes | None = None
        self._header: bytes | None = None
        self.recovered_from_prev = False

    def exists(self) -> bool:
        return self.path.exists() or self.prev_path.exists()

    @property
    def is_open(self) -> bool:
        return self.conn is not None

    # ---- 생성 / 열기 ------------------------------------------------
    def create(self, password: str | None = None) -> str:
        """새 저장소를 만들고 복구 키를 돌려준다.

        password 를 주면 이전 버전(v1) 형식으로 만든다(호환·시험용).
        """
        recovery = new_recovery_key()
        self._dek = secrets.token_bytes(32)
        rec_wrap = _wrap(_kek_recovery(recovery), self._dek)
        if password is None:
            self._header = _header_v2(rec_wrap, dpapi_protect(self._dek))
        else:
            salt = os.urandom(SALT_LEN)
            self._header = _header_v1(salt, _wrap(_kek_password(password, salt), self._dek), rec_wrap)
        self._load_plain(None)
        self._write()
        return recovery

    def open(self, password: str | None = None, recovery_key: str | None = None,
             device: bool = False):
        """device=True: 비밀번호 없이 이 PC에서 자동으로 연다."""
        self.recovered_from_prev = False
        try:
            blob = self.path.read_bytes()
            dek, header, plain = decrypt_blob(blob, password, recovery_key, device)
        except (CorruptFile, FileNotFoundError):
            if not self.prev_path.exists():
                raise
            blob = self.prev_path.read_bytes()
            dek, header, plain = decrypt_blob(blob, password, recovery_key, device)
            self.recovered_from_prev = True
        self._dek, self._header = dek, header
        self._load_plain(plain)
        if self.recovered_from_prev:
            self._write()

    def _load_plain(self, plain: bytes | None):
        if self.conn is not None:
            self.conn.close()
        conn = sqlite3.connect(":memory:")
        if plain:
            conn.deserialize(plain)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self.conn = conn

    # ---- 저장 -------------------------------------------------------
    def save(self):
        assert self.conn is not None
        self.conn.commit()
        self._write()

    def _write(self):
        assert self.conn is not None and self._dek and self._header
        plain = self.conn.serialize()
        nonce = os.urandom(12)
        ct = AESGCM(self._dek).encrypt(nonce, plain, self._header)
        blob = self._header + nonce + ct
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        if self.path.exists():
            prev_tmp = self.prev_path.with_suffix(".prevtmp")
            shutil.copyfile(self.path, prev_tmp)
            os.replace(prev_tmp, self.prev_path)
        os.replace(tmp, self.path)

    # ---- 전환 / 복원 ------------------------------------------------
    def set_device_key(self):
        """열려 있는 저장소를 '이 PC·이 Windows 계정으로 자동 열기' 형식(v2)으로 저장한다.

        복구 키로 감싼 키는 그대로 유지되므로 기존 복구 키와 백업은 계속 유효하다.
        """
        assert self._dek and self._header
        p = _parse(self._header, need_body=False)
        self._header = _header_v2(p.rec_wrap, dpapi_protect(self._dek))
        self._write()

    def replace_data(self, plain: bytes):
        """현재 키는 유지한 채 내용만 교체한다(백업 복원용)."""
        self._load_plain(plain)
        self._write()

    def export_container(self, dest: Path):
        """현재 암호화 파일을 그대로 복사(백업)한다."""
        self.conn.commit()
        self._write()
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, dest)

    def close(self):
        if self.conn is not None:
            try:
                self.conn.commit()
            finally:
                self.conn.close()
                self.conn = None
        self._dek = None
        self._header = None

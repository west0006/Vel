"""
数据加密工具模块。

提供 AES-256-GCM 加密/解密及 Windows DPAPI 密钥保护。
敏感字段（user_profile.value, episodic_memory.summary）在写入数据库前须加密。
"""

import base64
import os
import threading
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)
_key_lock = threading.Lock()


def _get_dpapi_key(key_path: str) -> bytes:
    """通过 Windows DPAPI 保护/读取加密密钥。

    首次调用时生成 32 字节随机密钥，通过 DPAPI 加密后保存。
    后续调用从文件读取 DPAPI 加密的密钥并解密。

    Args:
        key_path: 密钥文件路径

    Returns:
        32 字节 AES 密钥
    """
    key_file = Path(key_path)
    if key_file.exists():
        encrypted = key_file.read_bytes()
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
        except ImportError:
            logger.warning("win32crypt 不可用，回退到明文密钥存储")
            return encrypted[-32:]
    else:
        key = os.urandom(32)
        try:
            import win32crypt
            encrypted = win32crypt.CryptProtectData(
                key, "SmartDesktopPet_AES_Key", None, None, None, 0
            )
        except ImportError:
            logger.warning("win32crypt 不可用，密钥将以明文存储（仅开发环境！）")
            encrypted = key

        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(encrypted)
        logger.info(f"AES 密钥已生成并保存: {key_file}")

        # P1-10 修复：通过事件总线通知 UI 提示用户备份密钥
        _notify_key_generated(str(key_file))

        return key


def _notify_key_generated(key_path: str) -> None:
    """通知用户备份密钥（延迟导入避免循环依赖）。"""
    try:
        from core.event_bus import bus, EVENT_SYSTEM_STATUS
        bus.publish(EVENT_SYSTEM_STATUS, {
            "type": "key_generated",
            "path": key_path,
        })
    except Exception:
        # 事件总线可能尚未初始化——此时仅依赖日志
        logger.warning(
            f"加密密钥已生成，请手动备份到安全位置: {key_path}\n"
            f"如果此文件丢失，所有加密数据将永久无法解密！"
        )


def _get_aes_key() -> bytes:
    """获取 AES 密钥（线程安全单例）。"""
    with _key_lock:
        if not hasattr(_get_aes_key, "_key"):
            appdata = os.environ.get("APPDATA", os.path.expanduser("~/.config"))
            key_path = os.path.join(appdata, "SmartDesktopPet", "config", "key.bin")
            _get_aes_key._key = _get_dpapi_key(key_path)
        return _get_aes_key._key


def encrypt(plaintext: str) -> str:
    """使用 AES-256-GCM 加密字符串。"""
    if not plaintext:
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import secrets
        key = _get_aes_key()
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")
    except ImportError:
        logger.warning("cryptography 库未安装，使用明文替代（仅开发环境！）")
        return plaintext
    except Exception:
        logger.exception("加密失败")
        return plaintext


def decrypt(cipher_b64: str) -> str:
    """解密 AES-256-GCM 加密的字符串。"""
    if not cipher_b64:
        return ""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_aes_key()
        raw = base64.b64decode(cipher_b64)
        nonce = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except ImportError:
        logger.warning("cryptography 库未安装，直接返回（仅开发环境！）")
        return cipher_b64
    except Exception:
        logger.exception("解密失败")
        return cipher_b64


def safe_bool(value: str) -> bool:
    """将配置中的字符串值转换为布尔值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)
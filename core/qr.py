import secrets


def generate_qr_token():
    # 32 bytes → 64 hex chars
    return secrets.token_hex(32)

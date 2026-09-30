# app/services/wallet.py
from solders.keypair import Keypair
from app.core.security import encrypt_private_key, decrypt_private_key

class CustodialWalletEngine:
    @staticmethod
    def generate_custodial_wallet() -> dict:
        """Generates a new Solana keypair and returns public key + encrypted secret."""
        kp = Keypair()
        pubkey = str(kp.pubkey())
        raw_secret = bytes(kp)
        encrypted_secret = encrypt_private_key(raw_secret)
        
        return {
            "public_key": pubkey,
            "encrypted_private_key": encrypted_secret
        }

    @staticmethod
    def get_keypair_from_encrypted(encrypted_secret: str) -> Keypair:
        """Restores a usable Keypair object from stored encrypted string."""
        raw_bytes = decrypt_private_key(encrypted_secret)
        return Keypair.from_bytes(raw_bytes)
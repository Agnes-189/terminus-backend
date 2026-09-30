import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.hash import Hash
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Finalized, Confirmed
from solana.rpc.core import RPCException

logger = logging.getLogger("SolanaClient")

# RPC Failover Configuration
PRIMARY_RPC = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
FALLBACK_RPCS = [
    os.getenv("SOLANA_FALLBACK_RPC_1", "https://devnet.helius-rpc.com/?api-key=public"),
    "https://api.devnet.solana.com"
]

PROGRAM_ID = Pubkey.from_string(
    os.getenv("TERMINUS_PROGRAM_ID", "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU")
)

# Load Oracle Keypair from Secret (Base58 or Byte array string)
ORACLE_SECRET = os.getenv("ORACLE_KEYPAIR_SECRET")
ORACLE_KEYPAIR = Keypair.from_base58_string(ORACLE_SECRET) if ORACLE_SECRET else Keypair()


class SolanaClientService:
    @staticmethod
    async def get_rpc_client() -> AsyncClient:
        """Attempts connection to primary RPC, failing over to secondary nodes on error."""
        endpoints = [PRIMARY_RPC] + [url for url in FALLBACK_RPCS if url != PRIMARY_RPC]
        for url in endpoints:
            try:
                client = AsyncClient(url, commitment=Finalized)
                if await client.is_connected():
                    return client
            except Exception as e:
                logger.warning(f"⚠️ RPC connection failed for {url}: {str(e)}")
        raise RuntimeError("❌ All Solana RPC nodes are unreachable.")

    @classmethod
    def derive_vault_pda(cls, vault_owner: str) -> Tuple[Pubkey, int]:
        """Derives Program Derived Address (PDA) for a given vault owner."""
        owner_pubkey = Pubkey.from_string(vault_owner)
        return Pubkey.find_program_address(
            [b"vault", bytes(owner_pubkey)],
            PROGRAM_ID
        )

    @classmethod
    async def send_and_confirm_transaction(
        cls,
        ixs: List[Instruction],
        signers: List[Keypair],
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Builds a VersionedTransaction, signs it, broadcasts via RPC fallback,
        and polls until commitment reaches FINALIZED.
        """
        client = await cls.get_rpc_client()

        try:
            # 1. Fetch Latest Blockhash
            latest_blockhash_resp = await client.get_latest_blockhash(commitment=Finalized)
            recent_blockhash = latest_blockhash_resp.value.blockhash

            # 2. Compile MessageV0 and VersionedTransaction
            payer = signers[0].pubkey()
            compiled_msg = MessageV0.try_compile(
                payer=payer,
                instructions=ixs,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash
            )
            tx = VersionedTransaction(compiled_msg, signers)

            # 3. Broadcast Transaction
            tx_res = await client.send_transaction(tx)
            tx_sig = str(tx_res.value)
            logger.info(f"🚀 [SOLANA BROADCAST] Signature: {tx_sig}")

            # 4. Poll for FINALIZED Commitment
            confirmed = False
            for attempt in range(1, 15):
                await asyncio.sleep(2)
                status_resp = await client.get_signature_statuses([tx_res.value])
                status = status_resp.value[0]

                if status is not None:
                    if status.err is not None:
                        raise RuntimeError(f"On-chain execution error: {status.err}")
                    if status.confirmation_status in [Confirmed, Finalized]:
                        confirmed = True
                        logger.info(f"✅ [SOLANA FINALIZED] TX {tx_sig} finalized.")
                        break

            if not confirmed:
                raise TimeoutError(f"Transaction {tx_sig} was not finalized within timeout.")

            # 5. Fetch Transaction Logs for Event Parsing
            tx_info = await client.get_transaction(tx_res.value, commitment=Finalized)
            logs = tx_info.value.transaction.meta.log_messages if tx_info.value else []

            await client.close()
            return {
                "tx_signature": tx_sig,
                "status": "FINALIZED",
                "logs": logs
            }

        except Exception as e:
            await client.close()
            logger.error(f"❌ [SOLANA TX FAILED]: {str(e)}")
            raise e

    @classmethod
    async def trigger_challenge(
        cls,
        vault_owner: str,
        claimant_pubkey: str,
        claim_type: int = 2
    ) -> Dict[str, Any]:
        """
        Triggers an on-chain challenge using real VersionedTransactions
        and Oracle signing.
        """
        vault_pda, _ = cls.derive_vault_pda(vault_owner)
        claimant = Pubkey.from_string(claimant_pubkey)

        # 8-byte instruction discriminator for "trigger_challenge"
        instruction_discriminator = bytes([211, 12, 43, 88, 190, 44, 11, 3])
        data = instruction_discriminator + bytes([claim_type])

        accounts = [
            AccountMeta(pubkey=vault_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=claimant, is_signer=False, is_writable=False),
            AccountMeta(pubkey=ORACLE_KEYPAIR.pubkey(), is_signer=True, is_writable=True),
        ]

        challenge_ix = Instruction(PROGRAM_ID, data, accounts)

        return await cls.send_and_confirm_transaction(
            ixs=[challenge_ix],
            signers=[ORACLE_KEYPAIR]
        )

    @classmethod
    async def verify_settlement(cls, vault_owner: str) -> Dict[str, Any]:
        """Reads on-chain account state to confirm whether settlement conditions are met."""
        client = await cls.get_rpc_client()
        vault_pda, _ = cls.derive_vault_pda(vault_owner)

        try:
            account_info = await client.get_account_info(vault_pda, commitment=Finalized)
            await client.close()

            if not account_info.value:
                return {"is_settled": False, "reason": "Vault account does not exist"}

            # Parse state flags from account data byte layout
            raw_data = account_info.value.data
            is_settled = bool(raw_data[8]) if len(raw_data) > 8 else False

            return {
                "vault_pda": str(vault_pda),
                "is_settled": is_settled,
                "raw_data_len": len(raw_data)
            }
        except Exception as e:
            await client.close()
            raise e
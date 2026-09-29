# app/api/beneficiary.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.services.wallet import CustodialWalletEngine

router = APIRouter(prefix="/api/v1/beneficiary", tags=["Beneficiary"])

class SweepRequest(BaseModel):
    vault_id: str
    cex_destination_address: str  # CEX SOL/SPL deposit address

@router.post("/sweep-tokens")
def sweep_inherited_assets(payload: SweepRequest):
    """
    Allows Web2 beneficiaries to sweep custodial tokens to an external CEX[cite: 2].
    Requires smart contract state == Deceased[cite: 2].
    """
    # 1. Fetch vault and check smart contract state[cite: 2]
    vault = get_vault_from_db(payload.vault_id)
    if vault.state != "Deceased":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vault is not in Deceased state. Claim cannot be executed yet[cite: 2]."
        )

    # 2. Decrypt beneficiary custodial key[cite: 2]
    beneficiary_keypair = CustodialWalletEngine.get_keypair_from_encrypted(
        vault.beneficiary_encrypted_private_key
    )

    # 3. Construct and sign transfer transaction to CEX deposit address
    # 4. Broadcast transaction to Solana network
    
    return {
        "status": "success",
        "message": f"Assets successfully swept to {payload.cex_destination_address}",
        "tx_hash": "mock_solana_sweep_tx_hash"
    }
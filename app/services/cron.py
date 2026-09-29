# app/services/cron.py
import time
import logging
from sqlalchemy.orm import Session
from app.services.notifications import NotificationEngine
from app.services.oracle import HeartbeatOracleService

logger = logging.getLogger("terminus.cron")

def check_incapacitation_statuses(db_session: Session):
    """
    Continuous cron job checking user timestamps against current time.
    Triggers In_Challenge state on-chain and sends SMS/Email alerts.
    """
    now = int(time.time())
    
    # Query all active vaults from database
    # Vault model fields: id, owner_phone, next_of_kin_phone, last_active_timestamp, checkin_interval_sec, state
    active_vaults = db_session.query(VaultModel).filter(VaultModel.state == "Active").all()

    for vault in active_vaults:
        expiration_threshold = vault.last_active_timestamp + vault.checkin_interval_sec
        
        if now > expiration_threshold:
            logger.warning(f"Vault {vault.id} expired. Triggering Incapacitation protocol[cite: 2].")
            
            # 1. Oracle updates Solana PDA state to 'In_Challenge'[cite: 2]
            oracle = HeartbeatOracleService()
            oracle.update_vault_state_on_chain(vault.pda_address, new_state="In_Challenge")
            
            # 2. Update local DB state
            vault.state = "In_Challenge"
            db_session.commit()

            # 3. Dispatch automated alerts to Owner and Next of Kin[cite: 2]
            NotificationEngine.send_sms(
                to_phone=vault.owner_phone,
                message=f"[ALERT] Terminus Vault #{vault.id} entered In_Challenge state. Log in to cancel if alive[cite: 2]."
            )
            NotificationEngine.send_sms(
                to_phone=vault.next_of_kin_phone,
                message=f"[NOTICE] You have been designated as beneficiary for Terminus Vault #{vault.id}. Claim pending[cite: 2]."
            )
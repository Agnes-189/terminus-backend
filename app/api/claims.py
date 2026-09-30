from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.orchestrator import MasterOracleOrchestrator

router = APIRouter(prefix="/api/v1/claims", tags=["Claims Orchestrator"])


@router.post("/verify-and-trigger")
async def verify_and_trigger_claim(
    username: str = Form(...),
    vault_owner: str = Form(...),
    claimant_pubkey: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Triggers the Master Oracle Service Orchestrator:
    Document Validation -> ZK Generation -> Staging -> Solana Broadcast -> Audit Trail
    """
    try:
        file_bytes = await file.read()
        
        orchestrator = MasterOracleOrchestrator(db=db)
        result = await orchestrator.execute_claim_workflow(
            username=username,
            vault_owner=vault_owner,
            claimant_pubkey=claimant_pubkey,
            file_bytes=file_bytes,
            filename=file.filename
        )

        if result["status"] in ["FAILED", "ROLLED_BACK"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=result
            )

        return {"status": "success", "data": result}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Master Orchestrator execution error: {str(e)}"
        )
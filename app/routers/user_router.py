from fastapi.responses import JSONResponse, RedirectResponse
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, insert, delete, update, func
from sqlalchemy.orm import Session, selectinload
from app.db_setup import get_db
from fastapi import Depends, APIRouter, HTTPException, status, Response, Cookie, Request
from app.database.models import User, Session
from app.auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from uuid import uuid4
from app.auth import get_current_user
from app.routers.login_router import prepare_fastapi_request, init_saml_auth, SERVICE_PROVIDER_ENTITY_ID, FRONTEND_URL
from app.logging.logger import logger

router = APIRouter()



# @router.post("")
# async def login_for_access_token(
#     credentials: UserLoginSchema, db: Session = Depends(get_db)
# ) -> dict:
#     db_user =   db.scalars(
#         select(User).where(func.lower(User.email)  == func.lower(credentials.email) )
#     ).first()
#     user = authenticate_user(db_user, credentials.email, credentials.password)
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         user={"email": user.email, "id": user.id}, expires_delta=access_token_expires
#     )
#     return {"token": access_token, "type": "bearer"}






@router.get("/me")
async def whoami(
    request: Request,
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Get session from database
    session = db.query(Session).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )

    # Get user info
    user = db.query(User).filter_by(id=session.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "org": user.org,
        # Add any other user fields you want to expose
    }




# @router.post("/logout")
# async def logout(
#     request: Request,
#     db: Session = Depends(get_db),
#     session_id: str = Cookie(None)
# ):
#     # Get SAML session info from database
#     print("session_id ",session_id)
#     name_id = None
#     session_index = None
#     if session_id:
#         session_record = db.query(Session).filter_by(session_id=session_id).first()
#         if session_record:
#             # Retrieve SAML session information
#             name_id = session_record.saml_name_id  # You'll need to add this field to Session model
#             session_index = session_record.saml_session_index  # You'll need to add this field too
#             db.delete(session_record)
#             db.commit()
#     print("name_id ",name_id)
#     print("session_index ",session_index)
#     # Initiate SAML logout
#     req = await prepare_fastapi_request(request)
#     auth = init_saml_auth(req)
#     slo_url = auth.logout(name_id=name_id, session_index=session_index)
#     print( "slo_url ",slo_url)

#     response = RedirectResponse(url=slo_url)
#     # response = JSONResponse({"status": "logged_out"})
#     response.delete_cookie(key="session_id")
#     return response

@router.get("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    logger.info("Logout initiated for session_id: %s", session_id)
    name_id = None
    session_index = None
    
    # Get SAML session info before deleting
    if session_id:
        session_record = db.query(Session).filter_by(session_id=session_id).first()
        if session_record:
            name_id = session_record.saml_name_id
            session_index = session_record.saml_session_index
            logger.info("Found SAML session info - name_id: %s, session_index: %s", 
                       name_id, session_index)
            # Delete session after getting SAML info
            db.delete(session_record)
            db.commit()

    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)

    print("name_id ",name_id)
    print("session_index ",session_index)
    
    try:
        # Initiate SAML logout with explicit return URL to SLO endpoint
        slo_url = auth.logout(
            name_id=name_id,
            session_index=session_index,
            return_to=f"{SERVICE_PROVIDER_ENTITY_ID}/v1/users/slo"  # Explicit SLO endpoint
        )
        
        if not slo_url:
            logger.warning("No SLO URL returned from Okta, falling back to local logout")
            return RedirectResponse(
                url=FRONTEND_URL,
                status_code=status.HTTP_303_SEE_OTHER
            )
        
        logger.info("Redirecting to Okta SLO URL: %s", slo_url)
        response = RedirectResponse(
            url=slo_url,
            status_code=status.HTTP_303_SEE_OTHER
        )
        response.delete_cookie(
            key="session_id",
            path="/",
            secure=False,
            httponly=True,
            samesite="lax"
        )
        return response
        
    except Exception as e:
        logger.error(f"Error initiating SAML logout: {str(e)}")
        return RedirectResponse(
            url=FRONTEND_URL,
            status_code=status.HTTP_303_SEE_OTHER
        )

@router.get("/slo")
@router.post("/slo")
async def slo(request: Request, db: Session = Depends(get_db)):
    logger.info("SLO endpoint called with method: %s", request.method)
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    
    try:
        # Process the SAML logout response
        url = auth.process_slo(delete_session_cb=lambda: None)
        errors = auth.get_errors()
        
        if errors:
            logger.error("Errors during SLO processing: %s", errors)
        
        logger.info("SLO processing completed, redirecting to frontend")
        response = RedirectResponse(
            url=FRONTEND_URL,
            status_code=status.HTTP_303_SEE_OTHER
        )
        # Ensure cookie is deleted even if already deleted in /logout
        response.delete_cookie(
            key="session_id",
            path="/",
            secure=False,
            httponly=True,
            samesite="lax"
        )
        return response
        
    except Exception as e:
        logger.error(f"Error processing SLO: {str(e)}")
        return RedirectResponse(
            url=FRONTEND_URL,
            status_code=status.HTTP_303_SEE_OTHER
        )
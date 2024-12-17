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
from app.routers.login_router import prepare_fastapi_request, init_saml_auth, SERVICE_PROVIDER_ENTITY_ID
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

@router.get("/slo")
@router.post("/slo")
async def slo(request: Request, db: Session = Depends(get_db)):
    logger.info("SLO endpoint called with method: %s", request.method)
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    
    # Process the logout response
    logger.debug("Processing SLO with auth object")
    url = auth.process_slo(delete_session_cb=lambda: None)
    
    errors = auth.get_errors()
    logger.info("SLO process completed. Errors: %s, Redirect URL: %s", errors, url)
    
    if len(errors) == 0:
        if url is not None:
            logger.info("Redirecting to IdP URL: %s", url)
            return RedirectResponse(url=url)
        else:
            logger.info("No redirect URL provided, returning to home page")
            return RedirectResponse(url="/")
    else:
        error_reason = auth.get_last_error_reason()
        logger.error("SLO failed with error: %s", error_reason)
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_reason
        )
    
@router.get("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    logger.info("Logout initiated for session_id: %s", session_id)
    name_id = None
    session_index = None
    
    if session_id:
        session_record = db.query(Session).filter_by(session_id=session_id).first()
        if session_record:
            name_id = session_record.saml_name_id
            session_index = session_record.saml_session_index
            logger.debug("Found SAML session info - name_id: %s, session_index: %s", 
                        name_id, session_index)
            # Delete the session from database
            db.delete(session_record)
            db.commit()
            logger.info("Deleted session from database")
        else:
            logger.warning("No session record found for session_id: %s", session_id)

    # Initiate SAML logout
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    
    return_to_url = f"{SERVICE_PROVIDER_ENTITY_ID}/v1/users/slo"
    logger.debug("Initiating SAML logout with return URL: %s", return_to_url)
    
    # Get the SAML logout URL
    slo_url = auth.logout(
        name_id=name_id,
        session_index=session_index,
        return_to=return_to_url
    )
    
    logger.info("Generated SLO URL: %s", slo_url)

    if slo_url is None:
        logger.info("No SLO URL returned, performing local logout only")
        response = RedirectResponse(url="/")
        response.delete_cookie(key="session_id")
        return response

    # Redirect to IdP logout URL
    logger.info("Redirecting to IdP logout URL: %s", slo_url)
    # response = RedirectResponse(url=slo_url)
    response.delete_cookie(key="session_id")
    return response
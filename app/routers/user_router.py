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
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    
    # Process the logout response
    url = auth.process_slo(delete_session_cb=lambda: None)
    
    errors = auth.get_errors()
    if len(errors) == 0:
        if url is not None:
            return RedirectResponse(url=url)
        else:
            return RedirectResponse(url="/")  # Redirect to home page after successful logout
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=auth.get_last_error_reason()
        )
    
@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    name_id = None
    session_index = None
    
    if session_id:
        session_record = db.query(Session).filter_by(session_id=session_id).first()
        if session_record:
            name_id = session_record.saml_name_id
            session_index = session_record.saml_session_index
            # Delete the session from database
            db.delete(session_record)
            db.commit()

    # Initiate SAML logout
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    
    # Get the SAML logout URL
    slo_url = auth.logout(
        name_id=name_id,
        session_index=session_index,
        return_to=f"{SERVICE_PROVIDER_ENTITY_ID}/v1/users/slo"  # Specify return URL
    )

    if slo_url is None:
        # If no URL is returned, just do local logout
        response = RedirectResponse(url="/")
        response.delete_cookie(key="session_id")
        return response

    # Redirect to IdP logout URL
    response = RedirectResponse(url=slo_url)
    response.delete_cookie(key="session_id")
    return response
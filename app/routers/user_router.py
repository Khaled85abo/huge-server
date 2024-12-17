from fastapi.responses import JSONResponse
from app.database.schemas import UserLoginSchema, UserSchema
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, insert, delete, update, func
from sqlalchemy.orm import Session, selectinload
from app.db_setup import get_db
from fastapi import Depends, APIRouter, HTTPException, status, Response, Cookie
from app.database.models import User, Session
from app.auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from uuid import uuid4
from app.auth import get_current_user
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


@router.post("")
def login_user(db: Session, response: Response, user_id: int):
    session_id = str(uuid4())
    new_session = Session(session_id=session_id, user_id=user_id)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    # Set cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,       # True in production with HTTPS
        samesite="none"     # If cross-domain
    )
    return {"status": "ok"}

@router.post("/logout")
def logout(
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    if session_id:
        session_record = db.query(Session).filter_by(session_id=session_id).first()
        if session_record:
            db.delete(session_record)
            db.commit()

    # Clear the cookie
    response = JSONResponse({"status": "logged_out"})
    response.set_cookie(
        key="session_id",
        value="",
        httponly=True,
        secure=False,
        samesite="none",
        expires=0
    )
    return response


@router.get("/whoami")
def get_me(db: Session = Depends(get_db), session_id: str = Cookie(None)):
    return {"status": "ok"}
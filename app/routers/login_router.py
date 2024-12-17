from fastapi import Depends, APIRouter, HTTPException, status, Response, Cookie, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from app.logging import logger
import os
from app.db_setup import get_db
from app.database.models import User, Session
from uuid import uuid4

IDENTITY_PROVIDER_SINGLE_SIGN_ON_URL = os.getenv('IDENTITY_PROVIDER_SINGLE_SIGN_ON_URL')
IDENTITY_PROVIDER_ISSUER = os.getenv('IDENTITY_PROVIDER_ISSUER')
SERVICE_PROVIDER_ENTITY_ID = os.getenv('SERVICE_PROVIDER_ENTITY_ID')
IDENTITY_PROVIDER_METADATA_URL = os.getenv('IDENTITY_PROVIDER_METADATA_URL')
IDENTITY_PROVIDER_SIGNOUT = os.getenv('IDENTITY_PROVIDER_SIGNOUT')
idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(IDENTITY_PROVIDER_METADATA_URL)

router = APIRouter()


# Read the certificate file
with open('cert/saml.pem', 'r') as cert_file:
    cert_content = cert_file.read()
    # Remove header, footer and newlines
    cert_content = cert_content.replace('-----BEGIN CERTIFICATE-----\n', '')
    cert_content = cert_content.replace('-----END CERTIFICATE-----', '')
    cert_content = cert_content.replace('\n', '')

# SAML settings - store this in a separate config file
saml_settings = {
    "strict": True,
    "debug": True,
    "sp": {
        "entityId": f"{SERVICE_PROVIDER_ENTITY_ID}/v1/metadata/",
        "assertionConsumerService": {
            "url": f"{SERVICE_PROVIDER_ENTITY_ID}/v1/login/callback",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        },
        "singleLogoutService": {
            "url": f"{SERVICE_PROVIDER_ENTITY_ID}/v1/logout",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
        "x509cert": "",
        "privateKey": ""
    },
    "idp": {
        # Instead of manually configuring these values
        "entityId": IDENTITY_PROVIDER_ISSUER,  # Your Okta Entity ID
        "singleSignOnService": {
            "url": IDENTITY_PROVIDER_SINGLE_SIGN_ON_URL,  # Your Okta SSO URL
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "singleLogoutService": {
            "url": IDENTITY_PROVIDER_SIGNOUT,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "x509cert": cert_content  # Certificate from Okta
        # You can use the metadata URL
        # "metadata": IDENTITY_PROVIDER_METADATA_URL
        # "metadata": idp_data["idp"]
    }
}

def init_saml_auth(req):
    auth = OneLogin_Saml2_Auth(req, saml_settings)
    return auth

async def prepare_fastapi_request(request: Request):
    # Get form data
    form_data = {}
    print(request.method)
    if request.method == "POST":
        print("POST")
        try:
            form_data = await request.form()
            form_data = dict(form_data)
        except:
            form_data = {}

    return {
        'https': 'on' if request.url.scheme == 'https' else 'off',
        'http_host': request.headers.get('host', ''),
        'script_name': request.url.path,
        'get_data': dict(request.query_params),
        'post_data': form_data,  # Use the parsed form data
        'query_string': request.url.query
    }

@router.get("")
async def login(request: Request):
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    sso_built_url = auth.login()
    return RedirectResponse(sso_built_url)

@router.post("/callback")
async def login_callback(request: Request, response: Response, db: Session = Depends(get_db)):
    req = await prepare_fastapi_request(request)  # Make this async
    auth = init_saml_auth(req)
    auth.process_response()
    errors = auth.get_errors()

    if len(errors) != 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=', '.join(errors)
        )

    if not auth.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Get the user data from SAML assertion
    saml_attributes = auth.get_attributes()
    email = saml_attributes.get('email')[0]  # Adjust based on your Okta attribute mapping

    # Find or create user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Create new user if doesn't exist
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create session
    session_id = str(uuid4())
    new_session = Session(session_id=session_id, user_id=user.id)
    db.add(new_session)
    db.commit()

    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in production
        samesite="none"
    )

    return {"status": "ok"}

@router.get("/metadata/")
async def metadata():
    auth = OneLogin_Saml2_Auth({}, saml_settings)
    metadata = auth.get_settings().get_sp_metadata()
    errors = auth.get_settings().validate_metadata(metadata)

    if len(errors) == 0:
        return Response(
            content=metadata,
            media_type='text/xml'
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=', '.join(errors)
        )

@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    session_id: str = Cookie(None)
):
    # Clear local session
    if session_id:
        session_record = db.query(Session).filter_by(session_id=session_id).first()
        if session_record:
            db.delete(session_record)
            db.commit()

    # Initiate SAML logout
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)
    name_id = None
    session_index = None
    slo_url = auth.logout(name_id=name_id, session_index=session_index)

    response = RedirectResponse(url=slo_url)
    # response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(key="session_id")
    return response


@router.get("/whoami")
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
        # Add any other user fields you want to expose
    }

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


# @router.get("")
# def login(request: dict, db: Session = Depends(get_db), session_id: str = Cookie(None)):
#     return {"status": "ok"}

# @router.post("/callback")
# def login_callback(db: Session, response: Response, user_id: int):
#     session_id = str(uuid4())
#     new_session = Session(session_id=session_id, user_id=user_id)
#     db.add(new_session)
#     db.commit()
#     db.refresh(new_session)
    
#     # Set cookie
#     response.set_cookie(
#         key="session_id",
#         value=session_id,
#         httponly=True,
#         secure=False,       # True in production with HTTPS
#         samesite="none"     # If cross-domain
#     )
#     return {"status": "ok"}

# @router.post("/logout")
# def logout(
#     db: Session = Depends(get_db),
#     session_id: str = Cookie(None)
# ):
#     if session_id:
#         session_record = db.query(Session).filter_by(session_id=session_id).first()
#         if session_record:
#             db.delete(session_record)
#             db.commit()

#     # Clear the cookie
#     response = JSONResponse({"status": "logged_out"})
#     response.set_cookie(
#         key="session_id",
#         value="",
#         httponly=True,
#         secure=False,
#         samesite="none",
#         expires=0
#     )
#     return response
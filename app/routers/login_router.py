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
from datetime import datetime, timedelta

IDENTITY_PROVIDER_SINGLE_SIGN_ON_URL = os.getenv('IDENTITY_PROVIDER_SINGLE_SIGN_ON_URL')
IDENTITY_PROVIDER_ISSUER = os.getenv('IDENTITY_PROVIDER_ISSUER')
SERVICE_PROVIDER_ENTITY_ID = os.getenv('SERVICE_PROVIDER_ENTITY_ID')
IDENTITY_PROVIDER_METADATA_URL = os.getenv('IDENTITY_PROVIDER_METADATA_URL')
IDENTITY_PROVIDER_SIGNOUT = os.getenv('IDENTITY_PROVIDER_SIGNOUT')
idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(IDENTITY_PROVIDER_METADATA_URL)

router = APIRouter()

# Add this new environment variable at the top with other env vars
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')  # Default to localhost for development

def serialize_cert(cert_content):
    cert_content = cert_content.replace('-----BEGIN CERTIFICATE-----\n', '')
    cert_content = cert_content.replace('-----END CERTIFICATE-----', '')
    cert_content = cert_content.replace('\n', '')
    return cert_content

def get_cert_content(path:str):
    with open(path, 'r')as cert_file:
        cert_content = cert_file.read()
    return serialize_cert(cert_content)


# Read the certificate file
# with open('cert/saml.pem', 'r') as cert_file:
#     cert_content = cert_file.read()
#     # Remove header, footer and newlines
#     cert_content = serialize_cert(cert_content)

# SAML settings - store this in a separate config file
saml_settings = {
    "strict": True,
    "debug": True,
    "sp": {
        "entityId": f"{SERVICE_PROVIDER_ENTITY_ID}",
        "assertionConsumerService": {
            "url": f"{SERVICE_PROVIDER_ENTITY_ID}/v1/login/callback",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        },
        "singleLogoutService": {
            "url": f"{SERVICE_PROVIDER_ENTITY_ID}/v1/logout",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
        "x509cert": get_cert_content('cert/sp.crt'),
        "privateKey": get_cert_content('cert/sp.key')
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
        "x509cert": get_cert_content('cert/saml.pem'),  # Certificate from Okta
        # You can use the metadata URL
        # "metadata": IDENTITY_PROVIDER_METADATA_URL
        # "metadata": idp_data["idp"]
    },
        # Add security settings to request a session index
    "security": {
        "logoutRequestSigned": True,
        "wantMessagesSigned": True,
        "nameIdEncrypted": True,
        "wantNameIdEncrypted": False,
        "authnRequestsSigned": False,
        "logoutResponseSigned": False,
        "signMetadata": False,
        "wantAssertionsSigned": False,
        "wantNameId": True,  # Make sure this is True
        "wantAssertionsEncrypted": False,
        "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        "createSession": True  # Enable session creation

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
    print("\n=== SAML Debug ===")
    print(f"SP Entity ID: {saml_settings['sp']['entityId']}")
    print(f"ACS URL: {saml_settings['sp']['assertionConsumerService']['url']}")
    
    req = await prepare_fastapi_request(request)
    auth = init_saml_auth(req)

    
    try:
        auth.process_response()
        name_id = auth.get_nameid()
        session_index = auth.get_session_index()
        print(f"NameID: {name_id}")
        print(f"Session Index: {session_index}")
        print("Response processed successfully")
    except Exception as e:
        print(f"Error processing response: {str(e)}")
        # Get more details about the error
        print("Errors:", auth.get_errors())
        print("Last Error Reason:", auth.get_last_error_reason())
        raise HTTPException(status_code=401, detail=str(e))
    
    # Check for errors
    errors = auth.get_errors()
    if len(errors) != 0:
        print("5. SAML Errors:", errors)
        print("6. Last Error Reason:", auth.get_last_error_reason())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"SAML Errors: {', '.join(errors)}. Reason: {auth.get_last_error_reason()}"
        )

    # Check authentication
    is_authenticated = auth.is_authenticated()
    print("7. Is Authenticated:", is_authenticated)
    
    if not is_authenticated:
        print("8. Authentication failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Get user attributes
    try:
        saml_attributes = auth.get_attributes()
        print("9. SAML Attributes:", saml_attributes)
        email = saml_attributes.get('email', [None])[0]
        print("10. Extracted Email:", email)
    except Exception as e:
        print("Error getting attributes:", str(e))
        raise HTTPException(status_code=500, detail="Error extracting user data")

    # Debug settings
    print("\n=== SAML Settings ===")
    print("SP Entity ID:", saml_settings['sp']['entityId'])
    print("ACS URL:", saml_settings['sp']['assertionConsumerService']['url'])
    print("IDP Entity ID:", saml_settings['idp'].get('entityId'))
    print("========================\n")

    # Rest of your code...
    try:
        # Get user attributes from SAML response
        saml_attributes = auth.get_attributes()
        email = saml_attributes.get('email', [None])[0]
        firstname = saml_attributes.get('firstname', [None])[0]
        lastname = saml_attributes.get('lastname', [None])[0]
        
        # Find or create user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print("11. Creating new user")
            user = User(
                email=email,
                name=f"{firstname} {lastname}",
                org="MAX VI"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            print("11. Found existing user")

        # Create session with all required fields
        session_id = str(uuid4())
        new_session = Session(
            session_id=session_id,
            user_id=user.id,
            last_accessed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),  # Set expiration to 24 hours
            ip_address=request.client.host,
            is_active=True,
            user_agent=request.headers.get("user-agent", "Unknown"),
            saml_name_id=name_id,  # Add these new fields
            saml_session_index=session_index  # Add these new fields
        )
        db.add(new_session)
        db.commit()
        print("12. Session created:", session_id)

        # Modify the end of the function to redirect instead of returning JSON
        response = RedirectResponse(
            url=FRONTEND_URL,
            status_code=status.HTTP_303_SEE_OTHER
        )
        
        # Modified cookie settings for better compatibility
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=False,  # Set to True if using HTTPS
            samesite="lax",  # Changed from "none" to "lax" for better compatibility
            path="/",  # Added to ensure cookie is available across all paths
            max_age=86400  # Added 24-hour expiration (in seconds)
        )
        
        return response

    except Exception as e:
        print("Error in database operations:", str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metadata")
async def metadata():
    print("\n=== Metadata Debug ===")
    try:
        auth = OneLogin_Saml2_Auth({}, saml_settings)
        metadata = auth.get_settings().get_sp_metadata()
        print("Generated Metadata:", metadata)
        
        errors = auth.get_settings().validate_metadata(metadata)
        if len(errors) == 0:
            print("Metadata validation successful")
            return Response(
                content=metadata,
                media_type='text/xml'
            )
        else:
            print("Metadata validation errors:", errors)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=', '.join(errors)
            )
    except Exception as e:
        print("Error generating metadata:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


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
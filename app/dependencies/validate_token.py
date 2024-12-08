from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth import decode_token
security = HTTPBearer()

async def verify_token(http_authorization_credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = http_authorization_credentials.credentials
    # Add your token validation logic here
    decode_token(token=token)
    # if not token or token != "expected_token":  # Replace 'expected_token' with your logic for validation
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid or expired token",
    #     )
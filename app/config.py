base_url = "http://localhost:8000"
import os

if os.getenv("ENVIRONMENT"):
    backend_base_url = "http://localhost:8000"
    frontend_base_url = "http://localhost:5173"
else:
    backend_base_url = "https://smarderobe-1.onrender.com"
    frontend_base_url = "https://fascinating-lollipop-4279f7.netlify.app"

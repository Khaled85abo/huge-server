# main.py
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Default to 8000, or use Render's $PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)
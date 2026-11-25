"""
TaskFlow Backend API
====================
Ponto de entrada compatível com versões anteriores. O código vive no pacote `app/`.

    uvicorn task_manager_api:app --reload
    python task_manager_api.py
"""

import os

from app.main import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))

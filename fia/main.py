import uvicorn

from fia.config import get_settings


if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run("fia.api:app", host=cfg.api_host, port=cfg.api_port,
                reload=cfg.app_env == "development")

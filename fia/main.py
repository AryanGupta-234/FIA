import uvicorn


def main() -> None:
    from fia.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "fia.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    main()

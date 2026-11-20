from api_server_factory import AppConfig, create_app

app = create_app(
    AppConfig(
        strict_env=False,
        bootstrap_tenancy=False,
        load_plugins=True,
    )
)

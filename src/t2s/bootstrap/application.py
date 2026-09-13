from fastapi import FastAPI

from t2s.api.error_handlers import handle_t2s_error, handle_unexpected_error
from t2s.api.health_routes import router as health_router
from t2s.api.query_routes import router as query_router
from t2s.configuration import Settings, load_application_settings
from t2s.errors import T2SError
from t2s.observability import bind_request_correlation, configure_structured_logging


def create_application(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or load_application_settings()
    configure_structured_logging(application_settings.log_level)

    application = FastAPI(title=application_settings.app_name)
    application.state.settings = application_settings
    application.middleware("http")(bind_request_correlation)
    application.add_exception_handler(T2SError, handle_t2s_error)
    application.add_exception_handler(Exception, handle_unexpected_error)
    application.include_router(health_router)
    application.include_router(query_router)
    return application

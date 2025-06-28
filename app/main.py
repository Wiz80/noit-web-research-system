from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from contextlib import asynccontextmanager
import logging
import os

from app.config import settings
from app.database import engine, Base
from app.api.research_routes import router as research_router


# Configure logging for better visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable CrewAI debug logging
logging.getLogger('crewai').setLevel(logging.DEBUG)
logging.getLogger('crewai.flow').setLevel(logging.DEBUG)
logging.getLogger('crewai.agent').setLevel(logging.DEBUG)
logging.getLogger('crewai.task').setLevel(logging.DEBUG)
logging.getLogger('crewai.crew').setLevel(logging.DEBUG)

# Also enable for langchain components used by CrewAI
logging.getLogger('langchain').setLevel(logging.INFO)
logging.getLogger('langchain_core').setLevel(logging.INFO)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    
    # Startup
    logger.info("🚀 Application starting up...")
    
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise
    
    # Validate configuration
    try:
        _validate_configuration()
        logger.info("Configuration validation passed")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
    
    logger.info("🎉 Application startup complete")
    yield
    
    # Shutdown
    logger.info("🛑 Application shutting down...")


def _validate_configuration():
    """Validate critical configuration settings"""
    
    # Check required API keys based on environment
    if settings.app_env == "production":
        if not settings.perplexity_api_key:
            raise ValueError("Perplexity API key is required for production")
        
        if not any([
            settings.openai_api_key,
            settings.anthropic_api_key,
            settings.google_api_key,
            settings.deepseek_api_key
        ]):
            raise ValueError("At least one LLM API key is required for production")
    
    # Check MinIO configuration
    if not all([
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_bucket_name
    ]):
        raise ValueError("MinIO configuration is incomplete")
    
    logger.info("Configuration validation completed")


# Create FastAPI application
app = FastAPI(
    title="Web Research System",
    description="""
    # Web Research Multi-Agent System
    
    A comprehensive web research system powered by CrewAI that performs deep research investigations using:
    
    ## Key Features
    - **Intelligent Planning**: Checks for existing research to avoid duplication
    - **Multi-Agent Architecture**: Planning and execution agents work collaboratively
    - **Advanced Web Research**: Uses Perplexity API for comprehensive web research
    - **Multiple LLM Support**: OpenAI, Anthropic, Google, and DeepSeek
    - **Structured Storage**: Results saved in MinIO with full traceability
    - **RESTful API**: Complete CRUD operations for research management
    
    ## Workflow
    1. **Planning Agent**: Analyzes query, checks for similar research, creates structured investigation plan
    2. **Execution Agent**: Performs web research using Perplexity, saves results to MinIO
    3. **Database Tracking**: Full audit trail of investigations, tasks, and results
    
    ## Models Supported
    
    ### LLM Providers
    - **OpenAI**: gpt-4o-mini (default), gpt-4o, gpt-4-turbo, gpt-3.5-turbo
    - **Anthropic**: claude-3-haiku, claude-3-sonnet, claude-3-opus
    - **Google**: gemini-1.5-flash, gemini-1.5-pro, gemini-pro
    - **DeepSeek**: deepseek-chat, deepseek-coder
    
    ### Perplexity Models
    - **sonar-pro** (default): Balanced performance and cost
    - **sonar-deep-research**: Deep analysis with extensive research
    - **sonar-reasoning-pro**: Advanced reasoning capabilities
    - **sonar-reasoning**: Standard reasoning model
    
    ## Usage Examples
    
    ### Create a Research
    ```bash
    curl -X POST "http://localhost:8000/research/" \\
         -H "Content-Type: application/json" \\
         -d '{
           "query": "Latest trends in AI chatbots 2024",
           "directory_path": "ai-research/chatbots",
           "llm_provider": "openai",
           "llm_model": "gpt-4o-mini",
           "perplexity_model": "sonar-pro"
         }'
    ```
    
    ### Get Research Results
    ```bash
    curl "http://localhost:8000/research/1"
    ```
    
    ### Search Research History
    ```bash
    curl "http://localhost:8000/research/search/query?q=chatbots"
    ```
    """,
    version="1.0.0",
    contact={
        "name": "InfinityLab Research Team",
        "email": "research@infinitylab.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", "unknown")
        }
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests"""
    
    # Generate request ID
    import uuid
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    logger.info(
        "HTTP request started",
        method=request.method,
        url=str(request.url),
        request_id=request_id
    )
    
    response = await call_next(request)
    
    logger.info(
        "HTTP request completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        request_id=request_id
    )
    
    return response


# Include routers
app.include_router(research_router, prefix="/api/v1")


# Root endpoint
@app.get("/")
def read_root():
    """Root endpoint with basic information"""
    return {
        "message": "Web Research Multi-Agent System",
        "description": "AI-powered web research using CrewAI and Perplexity",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "api_prefix": "/api/v1",
        "endpoints": {
            "create_research": "POST /api/v1/research/",
            "get_research": "GET /api/v1/research/{id}",
            "list_researches": "GET /api/v1/research/",
            "update_research": "PUT /api/v1/research/{id}",
            "delete_research": "DELETE /api/v1/research/{id}",
            "search_researches": "GET /api/v1/research/search/query",
            "health_check": "GET /api/v1/research/health",
            "available_models": "GET /api/v1/research/models/available",
            "statistics": "GET /api/v1/research/statistics/overview"
        }
    }


# Health check endpoint
@app.get("/health")
def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "service": "web-research-system",
        "version": "1.0.0",
        "environment": settings.app_env,
        "database": "connected",
        "timestamp": "2024-01-01T00:00:00Z"  # You can use datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=(settings.app_env == "development"),
        log_level=settings.log_level.lower()
    ) 
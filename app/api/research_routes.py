from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import (
    ResearchCreateRequest,
    ResearchUpdateRequest,
    ResearchResponse,
    ResearchListResponse,
    ResearchStatus,
    LLMProvider,
    PerplexityModel
)
from app.services.research_service import research_service
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/", response_model=ResearchResponse, status_code=201)
async def create_research(
    research_request: ResearchCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new research investigation
    
    This endpoint:
    1. Creates a research record in the database
    2. Executes the CrewAI flow to perform web research
    3. Updates the database with research results
    
    Args:
        research_request: Research creation parameters
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        ResearchResponse with created research details
    """
    
    try:
        logger.info(f"Creating new research: {research_request.query}")
        
        # Create and execute research (this will run the CrewAI flow)
        research_response = await research_service.create_research(db, research_request)
        
        logger.info(f"Successfully created research with ID: {research_response.id}")
        
        return research_response
        
    except Exception as e:
        logger.error(f"Error creating research: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create research: {str(e)}"
        )


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: int,
    db: Session = Depends(get_db)
):
    """
    Get research by ID
    
    Args:
        research_id: Research ID
        db: Database session
        
    Returns:
        ResearchResponse with research details
        
    Raises:
        HTTPException: If research not found
    """
    
    research = research_service.get_research(db, research_id)
    
    if not research:
        raise HTTPException(
            status_code=404,
            detail=f"Research with ID {research_id} not found"
        )
    
    return research


@router.get("/", response_model=ResearchListResponse)
def list_researches(
    skip: int = Query(0, ge=0, description="Number of researches to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of researches to return"),
    status: Optional[ResearchStatus] = Query(None, description="Filter by research status"),
    directory_path: Optional[str] = Query(None, description="Filter by directory path"),
    db: Session = Depends(get_db)
):
    """
    Get list of researches with optional filtering
    
    Args:
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        status: Optional status filter
        directory_path: Optional directory path filter
        db: Database session
        
    Returns:
        ResearchListResponse with list of researches
    """
    
    return research_service.get_researches(
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        directory_path=directory_path
    )


@router.put("/{research_id}", response_model=ResearchResponse)
def update_research(
    research_id: int,
    research_update: ResearchUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update research by ID
    
    Args:
        research_id: Research ID
        research_update: Research update parameters
        db: Database session
        
    Returns:
        Updated ResearchResponse
        
    Raises:
        HTTPException: If research not found
    """
    
    research = research_service.update_research(db, research_id, research_update)
    
    if not research:
        raise HTTPException(
            status_code=404,
            detail=f"Research with ID {research_id} not found"
        )
    
    logger.info(f"Updated research {research_id}")
    
    return research


@router.delete("/{research_id}", status_code=204)
def delete_research(
    research_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete research by ID
    
    Args:
        research_id: Research ID
        db: Database session
        
    Raises:
        HTTPException: If research not found
    """
    
    success = research_service.delete_research(db, research_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Research with ID {research_id} not found"
        )
    
    logger.info(f"Deleted research {research_id}")


@router.get("/search/query", response_model=ResearchListResponse)
def search_researches(
    q: str = Query(..., min_length=1, description="Search query"),
    skip: int = Query(0, ge=0, description="Number of researches to skip"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of researches to return"),
    db: Session = Depends(get_db)
):
    """
    Search researches by query text
    
    Args:
        q: Search query string
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        db: Database session
        
    Returns:
        ResearchListResponse with matching researches
    """
    
    return research_service.search_researches(
        db=db,
        query=q,
        skip=skip,
        limit=limit
    )


@router.get("/directory/{directory_path:path}", response_model=List[ResearchResponse])
def get_researches_by_directory(
    directory_path: str,
    db: Session = Depends(get_db)
):
    """
    Get all researches in a specific directory
    
    Args:
        directory_path: Directory path to search
        db: Database session
        
    Returns:
        List of ResearchResponse objects
    """
    
    return research_service.get_research_by_directory(db, directory_path)


@router.get("/statistics/overview")
def get_research_statistics(
    db: Session = Depends(get_db)
):
    """
    Get research statistics and analytics
    
    Args:
        db: Database session
        
    Returns:
        Dictionary with research statistics
    """
    
    return research_service.get_research_statistics(db)


@router.get("/models/available")
def get_available_models():
    """
    Get available LLM and Perplexity models
    
    Returns:
        Dictionary with available models for each provider
    """
    
    from app.services.llm_service import llm_service
    from app.services.perplexity_service import perplexity_service
    
    return {
        "llm_providers": {
            "openai": llm_service.get_available_models(LLMProvider.OPENAI),
            "anthropic": llm_service.get_available_models(LLMProvider.ANTHROPIC),
            "google": llm_service.get_available_models(LLMProvider.GOOGLE),
            "deepseek": llm_service.get_available_models(LLMProvider.DEEPSEEK)
        },
        "perplexity_models": perplexity_service.get_available_models(),
        "default_settings": {
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "perplexity_model": "sonar-pro"
        }
    }


# Health check endpoint
@router.get("/health")
def health_check():
    """
    Health check endpoint for the research service
    
    Returns:
        Dictionary with service health status
    """
    
    return {
        "status": "healthy",
        "service": "web-research-system",
        "version": "1.0.0",
        "timestamp": "2024-01-01T00:00:00Z"  # You can use datetime.utcnow().isoformat()
    } 
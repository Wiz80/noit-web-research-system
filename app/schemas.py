from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class LLMProvider(str, Enum):
    """Available LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


class PerplexityModel(str, Enum):
    """Available Perplexity models"""
    SONAR_PRO = "sonar-pro"
    SONAR_DEEP_RESEARCH = "sonar-deep-research"
    SONAR_REASONING_PRO = "sonar-reasoning-pro"
    SONAR_REASONING = "sonar-reasoning"


class ResearchStatus(str, Enum):
    """Research status options"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Task status options"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


# Request Schemas
class ResearchCreateRequest(BaseModel):
    """Schema for creating a new research"""
    query: str = Field(..., description="The research question or topic to investigate")
    directory_path: str = Field(..., description="MinIO directory path where research will be stored")
    llm_provider: LLMProvider = Field(default=LLMProvider.OPENAI, description="LLM provider to use")
    llm_model: str = Field(default="gpt-4o-mini", description="Specific LLM model to use")
    perplexity_model: PerplexityModel = Field(default=PerplexityModel.SONAR_PRO, description="Perplexity model to use")
    max_planning_tasks: int = Field(default=8, ge=1, le=20, description="Maximum number of research tasks to create")


class ResearchUpdateRequest(BaseModel):
    """Schema for updating research"""
    status: Optional[ResearchStatus] = None
    directory_path: Optional[str] = None


class SimilarResearchCreate(BaseModel):
    """Schema for creating similar research relationship"""
    current_research_id: int = Field(..., description="ID of the current research")
    similar_research_id: int = Field(..., description="ID of the similar research")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score between 0.0 and 1.0")
    reason: str = Field(..., description="Reason for the similarity")


# New schema for research tasks with specific prompts
class ResearchTaskStructure(BaseModel):
    """Schema for research task with specific prompt"""
    task_question: str = Field(..., description="The research question/task")
    specific_prompt: str = Field(..., description="Specific prompt for Perplexity API tailored to this task")
    task_order: int = Field(..., description="Order of the task in the investigation")
    focus_area: str = Field(..., description="Main focus area of this research task")


# Response Schemas
class ResearchTaskResponse(BaseModel):
    """Schema for research task response"""
    id: int
    task_query: str
    task_order: int
    status: TaskStatus
    minio_file_path: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SimilarResearchResponse(BaseModel):
    """Schema for similar research response"""
    id: int
    similarity_description: Optional[str]
    is_sufficient: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ResearchResponse(BaseModel):
    """Schema for research response"""
    id: int
    query: str
    directory_path: str
    status: ResearchStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    llm_provider: str
    llm_model: str
    perplexity_model: str
    tasks: List[ResearchTaskResponse] = []
    similar_researches: List[SimilarResearchResponse] = []

    class Config:
        from_attributes = True


class ResearchListResponse(BaseModel):
    """Schema for research list response"""
    researches: List[ResearchResponse]
    total: int
    page: int
    page_size: int


# Flow-specific schemas
class ResearchPlanningResult(BaseModel):
    """Schema for research planning agent result"""
    has_similar_research: bool = Field(default=False, description="Whether similar research was found")
    similar_research_count: int = Field(default=0, description="Number of similar research found")
    has_valid_content: bool = Field(default=False, description="Whether similar research has valid content")
    existing_research_content: List[dict] = Field(default_factory=list, description="Content from existing similar research")
    investigation_structure: List[ResearchTaskStructure] = Field(default_factory=list, description="List of research tasks with specific prompts")
    proceed_with_research: bool = Field(default=True, description="Whether to proceed with new research")
    agent_analysis: Optional[str] = Field(default=None, description="Analysis from the planning agent")


class ResearchExecutionResult(BaseModel):
    """Schema for research execution agent result"""
    completed_tasks: List[ResearchTaskStructure] = Field(default_factory=list, description="List of completed research tasks")
    failed_tasks: List[ResearchTaskStructure] = Field(default_factory=list, description="List of failed research tasks")
    minio_files: List[str] = Field(default_factory=list, description="List of MinIO file paths created")
    success: bool = Field(default=True, description="Whether the execution was successful")


class FlowResult(BaseModel):
    """Schema for complete flow result"""
    research_id: int
    planning_result: ResearchPlanningResult
    execution_result: Optional[ResearchExecutionResult] = None
    status: ResearchStatus
    message: str 
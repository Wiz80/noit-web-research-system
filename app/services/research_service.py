from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models import Research, ResearchTask, SimilarResearch
from app.schemas import (
    ResearchCreateRequest, 
    ResearchUpdateRequest, 
    ResearchResponse, 
    ResearchListResponse,
    ResearchStatus,
    TaskStatus,
    FlowResult
)
from app.flows.research_flow import execute_research_flow
import structlog

logger = structlog.get_logger()


class ResearchService:
    """Service for managing research operations"""
    
    def __init__(self):
        logger.info(f"🔧 ResearchService initialized")
    
    async def create_research(
        self, 
        db: Session, 
        research_request: ResearchCreateRequest
    ) -> ResearchResponse:
        """
        Create a new research and execute the research flow
        
        Args:
            db: Database session
            research_request: Research creation request
            
        Returns:
            ResearchResponse with created research details
        """
        
        try:
            logger.info(f"🆕 Creating new research",
                       query=research_request.query,
                       directory_path=research_request.directory_path,
                       llm_provider=research_request.llm_provider.value,
                       llm_model=research_request.llm_model,
                       perplexity_model=research_request.perplexity_model.value,
                       max_planning_tasks=research_request.max_planning_tasks,
                       callback_enabled=research_request.callback_enabled,
                       callback_url=research_request.callback_url)
            
            logger.info(f"🔍 PERPLEXITY MODEL TRACKING: Received model '{research_request.perplexity_model.value}' from request")
            logger.info(f"📁 DIRECTORY PATH TRACKING: Received directory_path '{research_request.directory_path}' from request")
            
            # Create research record
            research = Research(
                query=research_request.query,
                directory_path=research_request.directory_path,
                status=ResearchStatus.PENDING.value,
                llm_provider=research_request.llm_provider.value,
                llm_model=research_request.llm_model,
                perplexity_model=research_request.perplexity_model.value,
                callback_enabled=research_request.callback_enabled,
                callback_url=research_request.callback_url,
                callback_data=research_request.callback_data
            )
            
            db.add(research)
            db.commit()
            db.refresh(research)
            
            logger.info(f"✅ Created research record", research_id=research.id)
            logger.info(f"📁 DIRECTORY PATH TRACKING: Stored in DB as '{research.directory_path}'")
            
            # Update status to in_progress
            research.status = ResearchStatus.IN_PROGRESS.value
            db.commit()
            
            logger.info(f"🔄 Updated research status to IN_PROGRESS", research_id=research.id)

            # Prepare inputs for the flow
            flow_inputs = {
                "research_id": research.id,
                "query": research_request.query,
                "directory_path": research_request.directory_path,
                "llm_provider": research_request.llm_provider.value,
                "llm_model": research_request.llm_model,
                "perplexity_model": research_request.perplexity_model.value,
                "max_planning_tasks": research_request.max_planning_tasks,
                "callback_enabled": research_request.callback_enabled,
                "callback_url": research_request.callback_url,
                "callback_data": research_request.callback_data
            }
            
            logger.info(f"📋 Prepared flow inputs",
                       research_id=research.id,
                       flow_inputs=flow_inputs)
            
            logger.info(f"🔍 PERPLEXITY MODEL TRACKING: Flow inputs contain model '{flow_inputs.get('perplexity_model')}'")
            logger.info(f"📁 DIRECTORY PATH TRACKING: Flow inputs contain directory_path '{flow_inputs.get('directory_path')}'")
            
            # Execute the research flow by passing the inputs dictionary and database session
            logger.info(f"🚀 Starting research flow execution", research_id=research.id)
            flow_result = await execute_research_flow(inputs=flow_inputs, db=db)
            logger.info(f"✅ Research flow execution completed",
                       research_id=research.id,
                       flow_success=flow_result.status == ResearchStatus.COMPLETED,
                       flow_status=flow_result.status.value,
                       flow_message=flow_result.message)
            
            # Update research with flow results
            logger.info(f"💾 Updating research with flow results", research_id=research.id)
            await self._update_research_with_flow_result(db, research, flow_result)
            
            # Refresh to get updated data
            db.refresh(research)
            
            logger.info(f"🎉 Research creation completed successfully",
                       research_id=research.id,
                       final_status=research.status)
            
            return ResearchResponse.from_orm(research)
            
        except Exception as e:
            logger.error(f"❌ Error creating research: {e}")
            
            # Update research status to failed if it exists
            if 'research' in locals() and research.id:
                research.status = ResearchStatus.FAILED.value
                db.commit()
                logger.info(f"🔄 Updated failed research status", research_id=research.id)
            
            raise
    
    def get_research(self, db: Session, research_id: int) -> Optional[ResearchResponse]:
        """
        Get research by ID
        
        Args:
            db: Database session
            research_id: Research ID
            
        Returns:
            ResearchResponse or None if not found
        """
        
        logger.info(f"🔍 Getting research by ID", research_id=research_id)
        
        research = db.query(Research).filter(Research.id == research_id).first()
        
        if research:
            logger.info(f"✅ Found research", research_id=research_id, status=research.status)
            return ResearchResponse.from_orm(research)
        
        logger.warning(f"❌ Research not found", research_id=research_id)
        return None
    
    def get_researches(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        status: Optional[ResearchStatus] = None,
        directory_path: Optional[str] = None
    ) -> ResearchListResponse:
        """
        Get list of researches with optional filtering
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            status: Optional status filter
            directory_path: Optional directory path filter
            
        Returns:
            ResearchListResponse with list of researches
        """
        
        query = db.query(Research)
        
        # Apply filters
        if status:
            query = query.filter(Research.status == status.value)
        
        if directory_path:
            query = query.filter(Research.directory_path == directory_path)
        
        # Get total count
        total = query.count()
        
        # Apply pagination and get results
        researches = query.offset(skip).limit(limit).all()
        
        return ResearchListResponse(
            researches=[ResearchResponse.from_orm(r) for r in researches],
            total=total,
            page=skip // limit + 1,
            page_size=limit
        )
    
    def update_research(
        self, 
        db: Session, 
        research_id: int, 
        research_update: ResearchUpdateRequest
    ) -> Optional[ResearchResponse]:
        """
        Update research by ID
        
        Args:
            db: Database session
            research_id: Research ID
            research_update: Research update request
            
        Returns:
            Updated ResearchResponse or None if not found
        """
        
        research = db.query(Research).filter(Research.id == research_id).first()
        
        if not research:
            return None
        
        # Update fields
        if research_update.status:
            research.status = research_update.status.value
        
        if research_update.directory_path:
            research.directory_path = research_update.directory_path
        
        research.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(research)
        
        logger.info(f"Updated research {research_id}")
        
        return ResearchResponse.from_orm(research)
    
    def delete_research(self, db: Session, research_id: int) -> bool:
        """
        Delete research by ID
        
        Args:
            db: Database session
            research_id: Research ID
            
        Returns:
            True if deleted, False if not found
        """
        
        research = db.query(Research).filter(Research.id == research_id).first()
        
        if not research:
            return False
        
        db.delete(research)
        db.commit()
        
        logger.info(f"Deleted research {research_id}")
        
        return True
    
    def search_researches(
        self, 
        db: Session, 
        query: str, 
        skip: int = 0, 
        limit: int = 50
    ) -> ResearchListResponse:
        """
        Search researches by query text
        
        Args:
            db: Database session
            query: Search query
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            ResearchListResponse with matching researches
        """
        
        # Search in research query field
        search_query = db.query(Research).filter(
            Research.query.ilike(f"%{query}%")
        )
        
        total = search_query.count()
        researches = search_query.offset(skip).limit(limit).all()
        
        return ResearchListResponse(
            researches=[ResearchResponse.from_orm(r) for r in researches],
            total=total,
            page=skip // limit + 1,
            page_size=limit
        )
    
    def get_research_by_directory(
        self, 
        db: Session, 
        directory_path: str
    ) -> List[ResearchResponse]:
        """
        Get all researches in a specific directory
        
        Args:
            db: Database session
            directory_path: Directory path to search
            
        Returns:
            List of ResearchResponse objects
        """
        
        researches = db.query(Research).filter(
            Research.directory_path == directory_path
        ).all()
        
        return [ResearchResponse.from_orm(r) for r in researches]
    
    async def _update_research_with_flow_result(
        self, 
        db: Session, 
        research: Research, 
        flow_result: FlowResult
    ) -> None:
        """
        Update research record with flow execution results
        
        Args:
            db: Database session
            research: Research record to update
            flow_result: Result from flow execution
        """
        
        try:
            logger.info(f"💾 Updating research with flow result",
                       research_id=research.id,
                       flow_status=flow_result.status.value,
                       has_planning_result=flow_result.planning_result is not None,
                       has_execution_result=flow_result.execution_result is not None)
            
            # Update research status
            research.status = flow_result.status.value
            research.completed_at = datetime.now(UTC) if flow_result.status in [
                ResearchStatus.COMPLETED, ResearchStatus.FAILED
            ] else None
            
            logger.info(f"🔄 Updated research status",
                       research_id=research.id,
                       new_status=research.status,
                       completed_at=research.completed_at)
            
            # Create research tasks from execution results
            if flow_result.execution_result and flow_result.execution_result.completed_tasks:
                logger.info(f"✅ Creating tasks for completed research",
                           research_id=research.id,
                           completed_tasks_count=len(flow_result.execution_result.completed_tasks))
                
                for i, task_structure in enumerate(flow_result.execution_result.completed_tasks, 1):
                    # Find corresponding MinIO file
                    minio_file = None
                    if i <= len(flow_result.execution_result.minio_files):
                        minio_file = flow_result.execution_result.minio_files[i-1]
                    
                    # Extract task query from ResearchTaskStructure or handle string for backward compatibility
                    if hasattr(task_structure, 'task_question'):
                        task_query_text = task_structure.task_question
                        task_order = task_structure.task_order
                    else:
                        # Backward compatibility for strings
                        task_query_text = str(task_structure)
                        task_order = i
                    
                    task = ResearchTask(
                        research_id=research.id,
                        task_query=task_query_text,
                        task_order=task_order,
                        status=TaskStatus.COMPLETED.value,
                        minio_file_path=minio_file,
                        completed_at=datetime.now(UTC)
                    )
                    db.add(task)
                    logger.info(f"📝 Created completed task",
                               research_id=research.id,
                               task_order=task_order,
                               minio_file=minio_file)
            
            # Create failed tasks
            if flow_result.execution_result and flow_result.execution_result.failed_tasks:
                logger.info(f"❌ Creating tasks for failed research",
                           research_id=research.id,
                           failed_tasks_count=len(flow_result.execution_result.failed_tasks))
                
                for i, task_structure in enumerate(flow_result.execution_result.failed_tasks, 1):
                    # Extract task query from ResearchTaskStructure or handle string for backward compatibility
                    if hasattr(task_structure, 'task_question'):
                        task_query_text = task_structure.task_question
                        task_order = task_structure.task_order
                    else:
                        # Backward compatibility for strings - extract original task query from failure message
                        task_query_text = str(task_structure)
                        if ": " in task_query_text:
                            task_query_text = task_query_text.split(": ", 1)[1]
                        task_order = len(flow_result.execution_result.completed_tasks) + i
                    
                    task = ResearchTask(
                        research_id=research.id,
                        task_query=task_query_text,
                        task_order=task_order,
                        status=TaskStatus.FAILED.value,
                        minio_file_path=None,
                        completed_at=datetime.now(UTC)
                    )
                    db.add(task)
                    logger.info(f"📝 Created failed task",
                               research_id=research.id,
                               task_order=task_order)
            
            # Create similar research records - only if we have similar research information
            if (flow_result.planning_result and 
                hasattr(flow_result.planning_result, 'has_similar_research') and 
                flow_result.planning_result.has_similar_research and
                flow_result.planning_result.similar_research_count > 0):
                
                logger.info(f"🔗 Creating similar research record",
                           research_id=research.id,
                           similar_count=flow_result.planning_result.similar_research_count)
                
                # Create a general similar research record
                similar_research = SimilarResearch(
                    research_id=research.id,
                    similarity_description=f"Found {flow_result.planning_result.similar_research_count} similar research(es)",
                    is_sufficient=not flow_result.planning_result.proceed_with_research
                )
                db.add(similar_research)
            
            # Commit all changes to database FIRST
            db.commit()
            logger.info(f"✅ Successfully updated research with flow results", research_id=research.id)
            
            # Send callback AFTER updating the status - only if research is completed or failed
            if research.callback_enabled and research.callback_url and research.status in [
                ResearchStatus.COMPLETED.value, ResearchStatus.FAILED.value
            ]:
                logger.info(f"📞 Sending callback after research completion",
                           research_id=research.id,
                           callback_url=research.callback_url,
                           final_status=research.status)
                
                try:
                    # Import callback service here to avoid circular imports
                    from app.services.callback_service import callback_service
                    
                    # Refresh research to get latest data including tasks
                    db.refresh(research)
                    
                    # Prepare research summary
                    research_summary = callback_service.prepare_research_summary(research)
                    
                    # Get research files
                    research_files = []
                    if research.tasks:
                        research_files = [task.minio_file_path for task in research.tasks if task.minio_file_path]
                    
                    # Send callback with the updated status
                    callback_success = await callback_service.send_research_callback(
                        db=db,
                        research=research,
                        research_content=research_summary,
                        research_files=research_files
                    )
                    
                    if callback_success:
                        logger.info(f"✅ Callback sent successfully for research {research.id}")
                    else:
                        logger.warning(f"⚠️ Failed to send callback for research {research.id}")
                        
                except Exception as callback_error:
                    logger.error(f"❌ Error sending callback for research {research.id}: {str(callback_error)}")
                    # Don't raise the error - callback failure shouldn't fail the research
            
        except Exception as e:
            logger.error(f"❌ Error updating research with flow result", research_id=research.id, error=str(e))
            db.rollback()
            raise
    
    def get_research_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Get research statistics
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with research statistics
        """
        
        total_researches = db.query(Research).count()
        
        # Count by status
        status_counts = {}
        for status in ResearchStatus:
            count = db.query(Research).filter(Research.status == status.value).count()
            status_counts[status.value] = count
        
        # Count by LLM provider
        llm_provider_counts = {}
        for provider in ["openai", "anthropic", "google", "deepseek"]:
            count = db.query(Research).filter(Research.llm_provider == provider).count()
            llm_provider_counts[provider] = count
        
        # Count by Perplexity model
        perplexity_model_counts = {}
        for model in ["sonar-pro", "sonar-deep-research", "sonar-reasoning-pro", "sonar-reasoning"]:
            count = db.query(Research).filter(Research.perplexity_model == model).count()
            perplexity_model_counts[model] = count
        
        # Recent researches (last 7 days)
        from datetime import timedelta
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)
        recent_researches = db.query(Research).filter(
            Research.created_at >= seven_days_ago
        ).count()
        
        return {
            "total_researches": total_researches,
            "status_distribution": status_counts,
            "llm_provider_distribution": llm_provider_counts,
            "perplexity_model_distribution": perplexity_model_counts,
            "recent_researches_7_days": recent_researches
        }


# Global research service instance
research_service = ResearchService() 
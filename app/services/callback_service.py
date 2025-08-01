import json
import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime, UTC
from sqlalchemy.orm import Session
from app.models import Research
from app.schemas import ResearchStatus
import structlog

logger = structlog.get_logger()


class CallbackService:
    """Service for handling research completion callbacks"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        logger.info(f"🔔 CallbackService initialized with timeout: {timeout}s")
    
    async def send_research_callback(
        self, 
        db: Session, 
        research: Research,
        research_content: Optional[str] = None,
        research_files: Optional[list] = None
    ) -> bool:
        """
        Send callback when research is completed
        
        Args:
            db: Database session
            research: Research instance
            research_content: Optional research content summary
            research_files: Optional list of generated files
            
        Returns:
            bool: True if callback was sent successfully, False otherwise
        """
        
        if not research.callback_enabled or not research.callback_url:
            logger.info(f"📴 Callback not enabled for research {research.id}")
            return False
        
        if research.callback_sent:
            logger.info(f"📤 Callback already sent for research {research.id}")
            return True
            
        try:
            logger.info(f"📞 Sending callback for research {research.id}",
                       callback_url=research.callback_url,
                       status=research.status)
            
            # Prepare callback payload
            callback_payload = {
                "research_id": research.id,
                "query": research.query,
                "status": research.status,
                "directory_path": research.directory_path,
                "created_at": research.created_at.isoformat() if research.created_at else None,
                "completed_at": research.completed_at.isoformat() if research.completed_at else None,
                "llm_provider": research.llm_provider,
                "llm_model": research.llm_model,
                "perplexity_model": research.perplexity_model,
            }
            
            # Add research content if available
            if research_content:
                callback_payload["research_content"] = research_content
            
            # Add research files if available
            if research_files:
                callback_payload["research_files"] = research_files
            
            # Add custom callback data if provided
            if research.callback_data:
                callback_payload.update(research.callback_data)
            
            # Add task information
            if research.tasks:
                callback_payload["tasks"] = [
                    {
                        "id": task.id,
                        "task_query": task.task_query,
                        "task_order": task.task_order,
                        "status": task.status,
                        "minio_file_path": task.minio_file_path,
                        "completed_at": task.completed_at.isoformat() if task.completed_at else None
                    }
                    for task in research.tasks
                ]
            
            logger.info(f"📋 Prepared callback payload",
                       research_id=research.id,
                       payload_keys=list(callback_payload.keys()))
            
            # Send HTTP callback
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Noit-Web-Research-System/1.0"
            }
            
            response = requests.post(
                research.callback_url,
                json=callback_payload,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Callback sent successfully",
                           research_id=research.id,
                           status_code=response.status_code)
                
                # Update research record
                research.callback_sent = True
                research.callback_sent_at = datetime.now(UTC)
                db.commit()
                
                return True
            else:
                logger.error(f"❌ Callback failed with status code",
                           research_id=research.id,
                           status_code=response.status_code,
                           response_text=response.text)
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"⏰ Callback timeout for research {research.id}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Callback request error for research {research.id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"💥 Unexpected error sending callback for research {research.id}: {str(e)}")
            return False
    
    def prepare_research_summary(self, research: Research) -> Optional[str]:
        """
        Prepare a summary of the research results
        
        Args:
            research: Research instance
            
        Returns:
            str: Research summary or None
        """
        
        if not research.tasks:
            return None
        
        completed_tasks = [task for task in research.tasks if task.status == "completed"]
        
        if not completed_tasks:
            return None
        
        summary_parts = []
        summary_parts.append(f"Research Query: {research.query}")
        summary_parts.append(f"Total Tasks: {len(research.tasks)}")
        summary_parts.append(f"Completed Tasks: {len(completed_tasks)}")
        
        if completed_tasks:
            summary_parts.append("\nCompleted Research Tasks:")
            for i, task in enumerate(completed_tasks, 1):
                summary_parts.append(f"{i}. {task.task_query}")
                if task.minio_file_path:
                    summary_parts.append(f"   File: {task.minio_file_path}")
        
        return "\n".join(summary_parts)


# Global callback service instance
callback_service = CallbackService() 
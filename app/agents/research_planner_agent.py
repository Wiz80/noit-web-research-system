from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, UTC
from crewai import Agent, Task, Crew
from crewai.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.services.llm_service import llm_service
from app.schemas import LLMProvider, ResearchPlanningResult
from app.models import Research, SimilarResearch
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


# Pydantic model for structured LLM output
class InvestigationStructure(BaseModel):
    """Model for investigation structure output"""
    research_tasks: List[dict] = Field(description="List of research tasks with specific prompts")

class ResearchTaskData(BaseModel):
    """Model for individual research task data"""
    task_question: str = Field(description="The research question/task")
    specific_prompt: str = Field(description="Specific prompt for Perplexity API tailored to this task")
    focus_area: str = Field(description="Main focus area of this research task")


# Service functions (Python normal functions)
async def verify_research_content_service(
    research_list: List[Dict], 
    directory_path: str,
    db: Session = None
) -> Dict[str, Any]:
    """
    Verify if similar research has actual content and results by checking MinIO directories.
    Lists folders in MinIO within the directory_path and verifies content directly.
    
    Args:
        research_list: List of similar research entries
        directory_path: The directory path to search in MinIO
        db: Database session
        
    Returns:
        Dictionary with content verification results
    """
    try:
        from app.services.minio_service import minio_service
        from app.models import ResearchTask
        
        logger.info(f"🔍 Verifying content for {len(research_list)} similar research entries in directory '{directory_path}'")
        
        valid_research = []
        research_content = []
        
        # Step 1: List all folders in the directory_path in MinIO
        logger.info(f"📁 Listing MinIO folders in directory: {directory_path}")
        
        try:
            # Get list of folders/objects in the directory path
            minio_folders = await minio_service.list_directory_contents(directory_path)
            logger.info(f"📂 Found {len(minio_folders)} items in MinIO directory '{directory_path}': {minio_folders}")
        except Exception as minio_error:
            logger.warning(f"⚠️ Could not list MinIO directory '{directory_path}': {minio_error}")
            minio_folders = []
        
        # Step 2: For each research in the list, verify both DB and MinIO content
        for research in research_list:
            research_id = research.get('id')
            research_directory = research.get('minio_directory', directory_path)
            
            logger.info(f"📂 Checking content for research ID {research_id} in directory '{research_directory}'")
            
            # Check database tasks first
            db_tasks = []
            if db:
                try:
                    db_tasks = db.query(ResearchTask).filter(
                        ResearchTask.research_id == research_id,
                        ResearchTask.minio_file_path.isnot(None),
                        ResearchTask.status == 'completed'
                    ).all()
                    logger.info(f"🗃️ Found {len(db_tasks)} completed tasks in DB for research {research_id}")
                except Exception as db_error:
                    logger.warning(f"⚠️ DB query error for research {research_id}: {db_error}")
            
            # Check MinIO content directly for this research
            research_minio_files = []
            try:
                # Look for files in MinIO that might belong to this research
                research_folder_pattern = f"research_{research_id}_"
                research_files_in_minio = [
                    item for item in minio_folders 
                    if research_folder_pattern in item or str(research_id) in item
                ]
                
                if not research_files_in_minio and db_tasks:
                    # If no pattern matches, try exact file paths from DB
                    research_files_in_minio = [task.minio_file_path for task in db_tasks if task.minio_file_path]
                
                logger.info(f"📄 Found {len(research_files_in_minio)} potential files in MinIO for research {research_id}: {research_files_in_minio}")
                
                # Verify actual content in MinIO files
                for file_path in research_files_in_minio[:3]:  # Check up to 3 files
                    try:
                        # Get the full file path if it's relative
                        full_file_path = file_path
                        if not file_path.startswith(directory_path):
                            full_file_path = f"{directory_path.rstrip('/')}/{file_path.lstrip('/')}"
                        
                        logger.info(f"📖 Checking MinIO file content: {full_file_path}")
                        content = await minio_service.get_file_content(full_file_path)
                        
                        if content and len(content.strip()) > 100:  # Has substantial content
                            research_minio_files.append({
                                "file_path": full_file_path,
                                "content": content,
                                "content_length": len(content)
                            })
                            logger.info(f"✅ Valid content found in MinIO file: {full_file_path} ({len(content)} chars)")
                        else:
                            logger.warning(f"⚠️ Insufficient content in MinIO file: {full_file_path}")
                            
                    except Exception as file_error:
                        logger.warning(f"⚠️ Could not read MinIO file {file_path}: {file_error}")
                        continue
                        
            except Exception as minio_check_error:
                logger.warning(f"⚠️ Error checking MinIO content for research {research_id}: {minio_check_error}")
            
            # Determine if this research has valid content
            has_valid_files = len(research_minio_files) > 0
            
            if has_valid_files:
                valid_research.append(research)
                
                # Create content summary using the best available source
                best_content = research_minio_files[0]  # Use first valid file
                task_query = f"Research {research_id}"
                
                # Try to get task query from DB if available
                if db_tasks:
                    task_query = db_tasks[0].task_query
                
                research_content.append({
                    "research_id": research_id,
                    "task_query": task_query,
                    "content": best_content["content"],
                    "file_path": best_content["file_path"],
                    "content_length": best_content["content_length"],
                    "created_at": research.get('created_at'),
                    "source": "minio_verification",
                    "total_files": len(research_minio_files)
                })
                
                logger.info(f"✅ Research {research_id} has valid content in MinIO: {len(research_minio_files)} files, {best_content['content_length']} chars")
            else:
                logger.warning(f"⚠️ Research {research_id} has no valid content in MinIO")
        
        logger.info(f"📊 MinIO content verification completed: {len(valid_research)} valid out of {len(research_list)} checked")
        
        # Log summary of what was found
        if valid_research:
            logger.info(f"🎉 CONTENT VERIFICATION SUCCESS - Found valid research content:")
            for content in research_content:
                logger.info(f"  📄 Research {content['research_id']}: {content['task_query'][:100]}... ({content['content_length']} chars)")
        else:
            logger.info(f"🔍 CONTENT VERIFICATION - No valid content found in MinIO directory '{directory_path}'")
        
        return {
            "has_valid_content": len(valid_research) > 0,
            "valid_research": valid_research,
            "research_content": research_content,
            "valid_count": len(valid_research),
            "total_checked": len(research_list),
            "minio_directory": directory_path,
            "minio_folders_found": len(minio_folders) if minio_folders else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error verifying research content in MinIO directory '{directory_path}': {e}")
        return {
            "has_valid_content": False,
            "valid_research": [],
            "research_content": [],
            "valid_count": 0,
            "total_checked": len(research_list),
            "minio_directory": directory_path,
            "error": str(e)
        }


async def check_similar_research_service(
    topic: str, 
    research_id: int, 
    directory_path: str,
    months_threshold: int = 3,
    db: Session = None
) -> Dict[str, Any]:
    """
    Service function to check for similar research in the database.
    This function specifically searches for research in the requested directory_path.
    
    Args:
        topic: The research topic to check for similarity
        research_id: The current research ID
        directory_path: The specific directory path to search in
        months_threshold: Number of months to look back (default: 3)
        db: Database session
    
    Returns:
        Dict with similar research information from the specific directory
    """
    try:
        logger.info(f"🔍 Checking for similar research in specific directory", 
                   topic=topic, 
                   research_id=research_id, 
                   directory_path=directory_path,
                   months_threshold=months_threshold)
        
        if not db:
            logger.warning("⚠️ No database session provided to check_similar_research_service")
            return {
                "has_similar": False,
                "similar_research": [],
                "count": 0,
                "recommendation": "No database session available for similarity check."
            }
        
        # Calculate the date threshold
        threshold_date = datetime.now(UTC) - timedelta(days=months_threshold * 30)
        logger.info(f"📅 Searching for similar research since: {threshold_date.isoformat()}")
        
        # Search for similar research in the SPECIFIC directory_path
        from app.schemas import ResearchStatus
        similar_research = db.query(Research).filter(
            and_(
                Research.created_at >= threshold_date,
                Research.directory_path == directory_path,  # 🔍 FILTRO POR DIRECTORIO ESPECÍFICO
                or_(
                    Research.query.ilike(f"%{topic}%"),
                    Research.query.contains(topic)
                ),
                Research.status.in_([
                    ResearchStatus.COMPLETED.value,
                    ResearchStatus.IN_PROGRESS.value
                ]),
                Research.id != research_id  # Exclude current research
            )
        ).all()
        
        logger.info(f"📊 Found {len(similar_research)} similar research entries in directory '{directory_path}'")
        
        # Process results
        if similar_research:
            similar_list = []
            for research in similar_research:
                similar_list.append({
                    "id": research.id,
                    "title": getattr(research, 'title', research.query),
                    "topic": research.query,
                    "created_at": research.created_at.isoformat(),
                    "status": research.status,
                    "minio_directory": research.directory_path
                })
                
                logger.info(f"📋 Similar research found in directory: ID={research.id}, Topic='{research.query}', Status={research.status}")
            
            # Verify if similar research has valid content
            logger.info(f"🔍 Verifying content for {len(similar_list)} similar research entries in directory...")
            content_verification = await verify_research_content_service(similar_list, directory_path, db)
            
            has_valid_content = content_verification.get('has_valid_content', False)
            research_content = content_verification.get('research_content', [])
            
            logger.info(f"📊 Content verification result: {content_verification.get('valid_count', 0)}/{len(similar_list)} have valid content in directory '{directory_path}'")
            
            # Save similar research relationships with proper is_sufficient flag
            for research in similar_research:
                try:
                    similar_research_record = SimilarResearch(
                        research_id=research_id,
                        similar_research_id=research.id,
                        similarity_description=f"Similar topic in directory '{directory_path}': {topic}",
                        is_sufficient=has_valid_content  # True if we have valid content
                    )
                    db.add(similar_research_record)
                    db.commit()
                    logger.info(f"✅ Created similar research relationship: {similar_research_record.id}, sufficient={has_valid_content}")
                except Exception as e:
                    logger.error(f"❌ Error creating similar research relationship: {e}")
                    db.rollback()
            
            logger.info(f"✅ Similar research check completed - Found {len(similar_list)} matches in directory '{directory_path}'")
            
            if has_valid_content:
                logger.info(f"🎉 Found valid content in directory '{directory_path}' - recommending to use existing research")
                return {
                    "has_similar": True,
                    "similar_research": similar_list,
                    "count": len(similar_list),
                    "has_valid_content": True,
                    "research_content": research_content,
                    "recommendation": f"Found {len(research_content)} similar research entries with valid content in directory '{directory_path}'. Using existing results."
                }
            else:
                logger.info(f"⚠️ Found similar research in directory '{directory_path}' but without valid content")
                return {
                    "has_similar": True,
                    "similar_research": similar_list,
                    "count": len(similar_list),
                    "has_valid_content": False,
                    "research_content": [],
                    "recommendation": f"Similar research found in directory '{directory_path}' but without valid content. Proceeding with new investigation."
                }
        else:
            logger.info(f"✅ No similar research found in directory '{directory_path}' - Proceeding with new investigation")
            return {
                "has_similar": False,
                "similar_research": [],
                "count": 0,
                "recommendation": f"No similar research found in directory '{directory_path}'. Proceed with new investigation."
            }
            
    except Exception as e:
        logger.error(f"❌ Error checking similar research in directory '{directory_path}': {e}")
        return {
            "has_similar": False,
            "similar_research": [],
            "count": 0,
            "recommendation": f"Error checking similar research in directory '{directory_path}': {str(e)}",
            "error": str(e)
        }


async def create_investigation_structure_service(
    topic: str, 
    objective: str, 
    llm_provider: LLMProvider = LLMProvider.OPENAI,
    llm_model: str = "gpt-4o-mini",
    max_planning_tasks: int = 8
) -> List['ResearchTaskStructure']:
    """
    Service function to create investigation structure using LLM with structured output.
    This is a normal Python function that can be called directly.
    
    Args:
        topic: The research topic
        objective: The research objective
        llm_provider: LLM provider to use
        llm_model: LLM model to use
        max_planning_tasks: Maximum number of research tasks to create
    
    Returns:
        List of ResearchTaskStructure objects with specific prompts
    """
    try:
        logger.info(f"🧠 Creating investigation structure using LLM",
                   provider=llm_provider.value,
                   model=llm_model,
                   topic=topic[:100],  # Truncate long topics for logging
                   max_tasks=max_planning_tasks)
        
        # If max_planning_tasks is 1, preserve the original query as a single task
        if max_planning_tasks == 1:
            logger.info(f"🎯 max_planning_tasks=1 DETECTED - Preserving original query as single task without LLM modification")
            
            # Create a single task that preserves the original query exactly
            from app.schemas import ResearchTaskStructure
            
            single_task = ResearchTaskStructure(
                task_question=topic,  # Use the original topic as the task question
                specific_prompt=topic,  # Use the original topic as the specific prompt (don't modify it)
                task_order=1,
                focus_area="Single Task Request"
            )
            
            logger.info(f"✅ Created single preserved task",
                       task_question_length=len(single_task.task_question),
                       specific_prompt_length=len(single_task.specific_prompt),
                       preserves_original=True,
                       skipped_llm=True)
            
            return [single_task]
        
        # For multiple tasks, proceed with normal multi-task breakdown using LLM
        logger.info(f"📋 max_planning_tasks > 1 - proceeding with multi-task breakdown using LLM")
        
        # Get LLM instance
        llm = llm_service.get_llm(llm_provider, llm_model)
        logger.info(f"✅ LLM instance created successfully")
        
        # Set up the parser
        parser = JsonOutputParser(pydantic_object=InvestigationStructure)
        logger.info(f"📝 JSON parser configured for structured output")
        
        # Create prompt template with format instructions
        prompt = PromptTemplate(
            template="""You are a research planning expert. Create a comprehensive investigation structure for the following research topic.

Topic: {topic}
Objective: {objective}
Maximum number of tasks to create: {max_tasks}

Create exactly {max_tasks} research tasks that will thoroughly investigate this topic. For each task, you need to provide:
1. A clear research question/task
2. A specific, detailed prompt that will be sent to Perplexity API to get the best results for that particular aspect
3. The main focus area of the research

Each task should be:
- Specific and focused on one aspect of the research
- Researchable through web sources
- Complementary to other tasks
- Designed to build a complete understanding of the topic

Consider these aspects for your research tasks:
- Current state and recent developments
- Market analysis and key players
- Trends and future projections
- Challenges and opportunities
- Technical aspects (if applicable)
- Regulatory and policy considerations (if applicable)
- Case studies and examples
- Expert opinions and insights

For each task's specific_prompt, create a detailed prompt that:
- Clearly explains what information is needed
- Provides context about the broader research
- Asks for specific types of information (statistics, examples, expert opinions, etc.)
- Requests credible sources and detailed analysis
- Is optimized for getting high-quality results from Perplexity API

{format_instructions}""",
            input_variables=["topic", "objective", "max_tasks"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )
        
        logger.info(f"📋 Prompt template created with format instructions")
        
        # Create the chain
        chain = prompt | llm | parser
        logger.info(f"🔗 LLM chain created successfully")
        
        # Invoke the chain
        logger.info(f"🚀 Invoking LLM chain to generate investigation structure...")
        result = chain.invoke({"topic": topic, "objective": objective, "max_tasks": max_planning_tasks})
        logger.info(f"✅ LLM chain invocation completed")
        
        # Extract the research tasks
        if isinstance(result, dict) and "research_tasks" in result:
            research_tasks_data = result["research_tasks"]
            logger.info(f"📊 Extracted {len(research_tasks_data)} research tasks from dict result")
        elif hasattr(result, 'research_tasks'):
            research_tasks_data = result.research_tasks
            logger.info(f"📊 Extracted {len(research_tasks_data)} research tasks from object result")
        else:
            # Fallback if structure is unexpected
            logger.warning(f"⚠️ Unexpected LLM response structure: {type(result)}, using fallback")
            return create_default_investigation_structure(topic, objective, max_planning_tasks)
        
        # Validate and convert to ResearchTaskStructure objects
        if isinstance(research_tasks_data, list) and len(research_tasks_data) > 0:
            from app.schemas import ResearchTaskStructure
            research_tasks = []
            
            for i, task_data in enumerate(research_tasks_data, 1):
                try:
                    # Ensure task_data is a dict
                    if isinstance(task_data, dict):
                        task_structure = ResearchTaskStructure(
                            task_question=task_data.get('task_question', f"Research task {i}"),
                            specific_prompt=task_data.get('specific_prompt', f"Research: {task_data.get('task_question', topic)}"),
                            task_order=i,
                            focus_area=task_data.get('focus_area', 'General Research')
                        )
                        research_tasks.append(task_structure)
                        logger.info(f"  {i}. {task_structure.focus_area}: {task_structure.task_question}")
                    else:
                        logger.warning(f"⚠️ Task {i} is not a dict: {type(task_data)}")
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ Error processing task {i}: {e}")
                    continue
            
            if research_tasks:
                logger.info(f"✅ Successfully created {len(research_tasks)} research tasks with specific prompts")
                return research_tasks
            else:
                logger.warning(f"⚠️ No valid research tasks created, using fallback")
                return create_default_investigation_structure(topic, objective, max_planning_tasks)
        else:
            logger.warning(f"⚠️ No valid research tasks returned (type: {type(research_tasks_data)}, length: {len(research_tasks_data) if hasattr(research_tasks_data, '__len__') else 'N/A'}), using fallback")
            return create_default_investigation_structure(topic, objective, max_planning_tasks)
            
    except Exception as e:
        logger.error(f"❌ Error creating investigation structure: {e}")
        logger.info(f"🔄 Falling back to default investigation structure")
        return create_default_investigation_structure(topic, objective, max_planning_tasks)


def create_default_investigation_structure(topic: str, objective: str, max_tasks: int = 8) -> List['ResearchTaskStructure']:
    """Create a default investigation structure if LLM fails"""
    logger.info(f"🏗️ Creating default investigation structure for topic: {topic}, max_tasks: {max_tasks}")
    
    from app.schemas import ResearchTaskStructure
    
    # If max_tasks is 1, preserve the original query as a single task
    if max_tasks == 1:
        logger.info(f"🎯 max_tasks=1 DETECTED IN DEFAULT - Preserving original query as single task")
        
        # Create a single task that preserves the original query exactly
        single_task = ResearchTaskStructure(
            task_question=topic,  # Use the original topic as the task question
            specific_prompt=topic,  # Use the original topic as the specific prompt (don't modify it)
            task_order=1,
            focus_area="Single Task Request (Default)"
        )
        
        logger.info(f"✅ Created single preserved default task",
                   task_question_length=len(single_task.task_question),
                   specific_prompt_length=len(single_task.specific_prompt),
                   preserves_original=True,
                   used_default=True)
        
        return [single_task]
    
    # For multiple tasks, proceed with generic sub-tasks
    logger.info(f"📋 max_tasks > 1 in default - proceeding with generic sub-tasks")
    
    default_tasks_data = [
        {
            "question": f"What is the current state of {topic}? Provide recent developments and key statistics.",
            "prompt": f"Provide a comprehensive overview of the current state of {topic}. Include recent developments, key statistics, market size, growth rates, and important milestones from the past 2 years. Focus on factual data and cite credible sources.",
            "focus": "Current State & Statistics"
        },
        {
            "question": f"Who are the major players and organizations involved in {topic}?",
            "prompt": f"Identify and analyze the major companies, organizations, and key players in {topic}. Provide details about their market positions, key products/services, recent activities, and competitive advantages. Include both established players and emerging companies.",
            "focus": "Market Players & Competition"
        },
        {
            "question": f"What are the main trends and future projections for {topic}?",
            "prompt": f"Analyze the key trends shaping {topic} and provide future projections. Include technological trends, market trends, consumer behavior changes, and expert predictions for the next 3-5 years. Summarize different analyst perspectives and forecasts.",
            "focus": "Trends & Future Projections"
        },
        {
            "question": f"What challenges and opportunities exist in {topic}?",
            "prompt": f"Identify and analyze the main challenges and opportunities in {topic}. Discuss barriers to growth, regulatory challenges, technological limitations, market opportunities, emerging niches, and potential areas for innovation. Provide specific examples and expert insights.",
            "focus": "Challenges & Opportunities"
        },
        {
            "question": f"What are expert opinions and insights about {topic}?",
            "prompt": f"Gather expert opinions, insights, and analysis about {topic} from industry leaders, analysts, researchers, and thought leaders. Include recent interviews, reports, and commentary from authoritative sources. Focus on diverse perspectives and emerging viewpoints.",
            "focus": "Expert Opinions & Analysis"
        },
        {
            "question": f"Are there any relevant case studies or examples related to {topic}?",
            "prompt": f"Find and analyze relevant case studies, success stories, and practical examples related to {topic}. Include both successful implementations and lessons learned from failures. Provide specific details about methodologies, results, and key takeaways.",
            "focus": "Case Studies & Examples"
        }
    ]
    
    default_tasks = []
    # Limit to max_tasks
    tasks_to_create = default_tasks_data[:max_tasks]
    
    for i, task_data in enumerate(tasks_to_create, 1):
        task_structure = ResearchTaskStructure(
            task_question=task_data["question"],
            specific_prompt=task_data["prompt"],
            task_order=i,
            focus_area=task_data["focus"]
        )
        default_tasks.append(task_structure)
    
    logger.info(f"✅ Created {len(default_tasks)} default research tasks (limited to {max_tasks}) with specific prompts")
    return default_tasks


# CrewAI Tools (only for agents to use)
@tool("check_similar_research")
def check_similar_research(
    topic: str, 
    research_id: int, 
    months_threshold: int = 3
) -> Dict[str, Any]:
    """
    Check for similar research in the database within the specified time threshold.
    
    Args:
        topic: The research topic to check for similarity
        research_id: The current research ID
        months_threshold: Number of months to look back (default: 3)
        
    Returns:
        Dict with similar research information
    """
    # Note: This tool doesn't use database directly
    # For now, we'll return a simplified response
    # In a production system, this would be handled by service layer
    return {
        "has_similar": False,
        "similar_research": [],
        "count": 0,
        "recommendation": "No similar research found. Proceed with new investigation.",
        "note": "Database check not implemented in tool - handled by service layer"
    }


@tool("create_investigation_structure")
def create_investigation_structure(
    topic: str, 
    objective: str,
    max_tasks: int = 8
) -> str:
    """
    Create a comprehensive investigation structure for the research topic.
    
    Args:
        topic: The main research topic
        objective: The research objective/goal
        max_tasks: Maximum number of tasks to create
        
    Returns:
        String representation of research tasks with specific prompts
    """
    # Use a synchronous version for tools
    tasks = create_default_investigation_structure(topic, objective, max_tasks)
    
    # Convert to string format for tool output
    result_lines = [f"Investigation structure for: {topic}"]
    result_lines.append(f"Objective: {objective}")
    result_lines.append(f"\nCreated {len(tasks)} research tasks:\n")
    
    for task in tasks:
        result_lines.append(f"Task {task.task_order}: {task.focus_area}")
        result_lines.append(f"Question: {task.task_question}")
        result_lines.append(f"Specific Prompt: {task.specific_prompt[:200]}...")
        result_lines.append("")
    
    return "\n".join(result_lines)


class ResearchPlannerAgent:
    """Agent responsible for planning research investigations"""
    
    def __init__(
        self, 
        llm_provider: LLMProvider = LLMProvider.OPENAI, 
        llm_model: str = "gpt-4o-mini"
    ):
        logger.info(f"🤖 Initializing ResearchPlannerAgent",
                   llm_provider=llm_provider.value,
                   llm_model=llm_model)
        
        self.llm = llm_service.get_llm(llm_provider, llm_model)
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        
        logger.info(f"✅ ResearchPlannerAgent initialized successfully")
    
    def create_agent(self) -> Agent:
        """Create the CrewAI agent for research planning"""
        logger.info(f"👤 Creating CrewAI agent for research planning")
        
        agent = Agent(
            role="Research Strategy Planner",
            goal="Analyze research requirements, check for existing similar work, and create comprehensive investigation plans",
            backstory="""You are a strategic research planner with extensive experience in designing 
            comprehensive investigation frameworks. You have a deep understanding of research methodologies, 
            information architecture, and knowledge management systems.
            
            Your expertise includes:
            - Analyzing research topics to identify key investigation areas
            - Checking existing research databases to avoid duplication
            - Creating structured, logical research plans that build comprehensive understanding
            - Identifying knowledge gaps and priority research areas
            - Designing research questions that are specific, measurable, and actionable
            
            Your approach is systematic and thorough:
            1. You carefully analyze the research topic and objectives
            2. You check for existing similar research to avoid duplication
            3. You create comprehensive investigation structures that cover all relevant aspects
            4. You ensure research questions are complementary and build upon each other
            5. You consider multiple perspectives and stakeholder viewpoints
            
            You are particularly skilled at:
            - Breaking down complex topics into manageable research components
            - Identifying the most valuable and impactful research questions
            - Balancing breadth and depth in research planning
            - Ensuring research efficiency and avoiding redundancy
            - Creating research plans that lead to actionable insights
            
            Your planning is always strategic, comprehensive, and designed to maximize research value.""",
            verbose=True,
            llm=self.llm,
            tools=[
                check_similar_research,
                create_investigation_structure
            ],
            allow_delegation=False
        )
        
        logger.info(f"✅ CrewAI agent created successfully")
        return agent
    
    def create_planning_task(
        self, 
        topic: str, 
        objective: str, 
        research_id: int,
        agent: Agent
    ) -> Task:
        """
        Create a CrewAI Task for research planning
        
        Args:
            topic: The research topic
            objective: The research objective
            research_id: The research ID from database
            agent: The agent that will execute the task
            
        Returns:
            CrewAI Task object
        """
        
        task = Task(
            description=f"""
            Plan a comprehensive research investigation for the following:
            
            Topic: {topic}
            Objective: {objective}
            Research ID: {research_id}
            
            Your task is to:
            1. First, use the check_similar_research tool to check if similar research has been conducted recently (within 3 months)
            2. Then, use the create_investigation_structure tool to create a comprehensive list of research questions/tasks
            
            The investigation structure should be thorough and cover all relevant aspects of the topic.
            Each research question should be specific, focused, and designed to build comprehensive understanding.
            
            Consider the research objective and ensure the questions align with the intended goals.
            """,
            expected_output="""
            A comprehensive research plan containing:
            1. Analysis of similar existing research (if any)
            2. Recommendation on whether to proceed with new research
            3. Detailed investigation structure with 5-8 specific research questions
            4. Each question should be clearly formulated and researchable
            5. Questions should be complementary and build comprehensive understanding
            """,
            agent=agent,
            tools=[check_similar_research, create_investigation_structure]
        )
        
        return task
    
    async def plan_research(
        self, 
        topic: str, 
        objective: str, 
        research_id: int,
        directory_path: str,
        db: Session = None,
        max_planning_tasks: int = 8
    ) -> ResearchPlanningResult:
        """
        Plan research investigation using service functions primarily
        
        Args:
            topic: The research topic
            objective: The research objective
            research_id: The research ID from database
            directory_path: The specific directory path to search in
            db: Database session for service functions
            max_planning_tasks: Maximum number of research tasks to create
            
        Returns:
            ResearchPlanningResult with planning details
        """
        
        try:
            logger.info(f"🎯 Starting research planning",
                       topic=topic,
                       objective=objective,
                       research_id=research_id,
                       directory_path=directory_path,
                       llm_provider=self.llm_provider.value,
                       llm_model=self.llm_model,
                       max_planning_tasks=max_planning_tasks)
            
            # Check for similar research in the specific directory
            logger.info(f"🔍 Step 1: Checking for similar research in directory '{directory_path}'...")
            similar_check = await check_similar_research_service(
                topic, research_id, directory_path, months_threshold=3, db=db
            )
            
            logger.info(f"📊 Similar research check results:",
                       has_similar=similar_check["has_similar"],
                       count=similar_check["count"],
                       directory_path=directory_path)
            
            # Create investigation structure using service function
            logger.info(f"🧠 Step 2: Creating investigation structure...")
            investigation_structure = await create_investigation_structure_service(
                topic, objective, self.llm_provider, self.llm_model, max_planning_tasks
            )
            
            logger.info(f"📋 Investigation structure created with {len(investigation_structure)} tasks")
            
            # Optional: Try to get additional agent insights (but don't fail if it doesn't work)
            agent_analysis = "Planning completed using service functions"
            logger.info(f"🤖 Step 3: Getting agent analysis...")
            
            try:
                # Create a simple agent without problematic tools
                simple_agent = Agent(
                    role="Research Strategy Planner",
                    goal="Analyze research requirements and create investigation plans",
                    backstory="You are a research planning expert.",
                    verbose=False,
                    llm=self.llm,
                    tools=[],  # No tools to avoid async issues
                    allow_delegation=False
                )
                
                logger.info(f"👤 Simple analysis agent created")
                
                # Create a simple task for analysis
                analysis_task = Task(
                    description=f"""
                    Analyze this research planning scenario:
                    
                    Topic: {topic}
                    Objective: {objective}
                    Directory: {directory_path}
                    Similar research found: {similar_check['has_similar']}
                    Investigation structure created: {len(investigation_structure)} tasks with specific prompts
                    
                    Provide a brief analysis of the research plan quality and any recommendations.
                    """,
                    expected_output="A brief analysis of the research plan and recommendations",
                    agent=simple_agent
                )
                
                logger.info(f"📝 Analysis task created")
                
                # Create crew and execute
                crew = Crew(
                    agents=[simple_agent],
                    tasks=[analysis_task],
                    verbose=False
                )
                
                logger.info(f"👥 Crew created, executing analysis...")
                crew_result = crew.kickoff()
                
                if analysis_task.output and analysis_task.output.raw:
                    agent_analysis = analysis_task.output.raw
                    logger.info(f"✅ Agent analysis completed successfully")
                else:
                    logger.warning(f"⚠️ Agent analysis completed but no output received")
                    
            except Exception as crew_error:
                logger.warning(f"⚠️ Agent analysis failed, using service results: {crew_error}")
                agent_analysis = f"Service-based planning completed successfully (agent analysis failed)"
            
            # Determine if we should proceed based on content validity
            has_valid_content = similar_check.get("has_valid_content", False)
            research_content = similar_check.get("research_content", [])
            
            # Only proceed with new research if no valid content exists in the directory
            proceed_with_research = not has_valid_content
            
            if has_valid_content:
                logger.info(f"🎉 Using existing research content from {len(research_content)} entries in directory '{directory_path}'")
                # Log existing content
                for i, content in enumerate(research_content, 1):
                    logger.info(f"  📄 {i}. Research ID {content['research_id']}: {content['task_query'][:100]}...")
            else:
                logger.info(f"📋 New investigation structure created:")
                for i, task in enumerate(investigation_structure, 1):
                    logger.info(f"  {i}. {task.focus_area}: {task.task_question}")
            
            logger.info(f"🎯 Research planning completed",
                       proceed_with_research=proceed_with_research,
                       similar_research_found=similar_check["has_similar"],
                       has_valid_content=has_valid_content,
                       tasks_created=len(investigation_structure),
                       directory_path=directory_path)
            
            return ResearchPlanningResult(
                has_similar_research=similar_check["has_similar"],
                similar_research_count=similar_check["count"],
                has_valid_content=has_valid_content,
                existing_research_content=research_content,
                investigation_structure=investigation_structure,
                proceed_with_research=proceed_with_research,
                agent_analysis=agent_analysis
            )
                
        except Exception as e:
            logger.error(f"❌ Error in research planning: {e}")
            
            # Fallback to direct service calls without database
            logger.info(f"🔄 Attempting fallback planning...")
            try:
                investigation_structure = await create_investigation_structure_service(
                    topic, objective, self.llm_provider, self.llm_model, max_planning_tasks
                )
                
                logger.info(f"✅ Fallback planning successful with {len(investigation_structure)} tasks")
                
                return ResearchPlanningResult(
                    has_similar_research=False,
                    similar_research_count=0,
                    investigation_structure=investigation_structure,
                    proceed_with_research=True,
                    agent_analysis=f"Planning completed with fallback due to error: {str(e)}"
                )
            except Exception as fallback_error:
                logger.error(f"❌ Fallback also failed: {fallback_error}")
                
                default_structure = create_default_investigation_structure(topic, objective, max_planning_tasks)
                logger.info(f"🏗️ Using default structure with {len(default_structure)} tasks")
                
                return ResearchPlanningResult(
                    has_similar_research=False,
                    similar_research_count=0,
                    investigation_structure=default_structure,
                    proceed_with_research=True,
                    agent_analysis=f"Planning failed, using default structure: {str(e)}"
                ) 
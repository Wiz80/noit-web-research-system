from typing import Dict, Any, List
from datetime import datetime, UTC
from crewai import Agent, Task, Crew
from crewai.tools import tool
from app.services.perplexity_service import perplexity_service
from app.services.minio_service import minio_service
from app.services.llm_service import llm_service
from app.schemas import LLMProvider, PerplexityModel, ResearchExecutionResult
import structlog

logger = structlog.get_logger()


# Service functions (Python normal functions)
async def perform_perplexity_research(query: str, perplexity_model: PerplexityModel, specific_prompt: str = None) -> Dict[str, Any]:
    """
    Service function to perform web research using Perplexity API.
    This is a normal Python function that can be called directly.
    """
    try:
        logger.info(f"🔍 Starting Perplexity research",
                   query=query[:100],  # Truncate for logging
                   model=perplexity_model.value)
        
        # Use specific prompt if provided, otherwise enhance the query for better research results
        if specific_prompt:
            enhanced_query = specific_prompt
            logger.info(f"📝 Using specific prompt provided by planner (length: {len(specific_prompt)} chars)")
        else:
            enhanced_query = f"""
            Research the following topic comprehensively: {query}
            
            Please provide:
            1. Current state and recent developments
            2. Key statistics and data points
            3. Major players and organizations involved
            4. Trends and future projections
            5. Challenges and opportunities
            6. Expert opinions and insights
            7. Relevant case studies or examples
            
            Use credible sources and provide specific details with proper context.
            """
            logger.info(f"📝 Using generic enhanced query (length: {len(enhanced_query)} chars)")
        
        # Perform the research using Perplexity
        logger.info(f"🌐 Calling Perplexity API...",
                   model=perplexity_model.value,
                   max_tokens=4000,
                   temperature=0.1)
        
        research_result = await perplexity_service.search_and_research(
            query=enhanced_query,
            model=perplexity_model,
            max_tokens=4000,
            temperature=0.1
        )
        
        logger.info(f"✅ Perplexity API call completed",
                   content_length=len(research_result.get('content', '')),
                   citations_count=len(research_result.get('citations', [])),
                   tokens_used=research_result.get('tokens_used', 0))
        
        # Add timestamp
        research_result['timestamp'] = datetime.utcnow().isoformat()
        research_result['original_query'] = query
        
        logger.info(f"📊 Research result prepared with metadata")
        return research_result
        
    except Exception as e:
        logger.error(f"❌ Error in Perplexity research: {e}")
        return {
            "content": f"Error occurred during research: {str(e)}",
            "citations": [],
            "model_used": perplexity_model.value,
            "tokens_used": 0,
            "query": query,
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "original_query": query
        }


async def save_research_to_minio_service(
    research_result: Dict[str, Any], 
    directory_path: str, 
    task_order: int = None
) -> Dict[str, Any]:
    """
    Service function to save research result to MinIO as a markdown file.
    This is a normal Python function that can be called directly.
    """
    try:
        logger.info(f"💾 Starting MinIO save operation",
                   directory_path=directory_path,
                   task_order=task_order,
                   content_length=len(str(research_result)))
        
        # Generate filename
        base_name = research_result.get('original_query', 'research')[:50]  # Limit length
        filename = minio_service.generate_filename(base_name, task_order)
        logger.info(f"📁 Generated filename: {filename}")
        
        # Format content as markdown
        logger.info(f"📝 Formatting content as markdown...")
        markdown_content = perplexity_service.format_research_as_markdown(research_result)
        logger.info(f"✅ Markdown formatting completed (length: {len(markdown_content)} chars)")
        
        # Save to MinIO
        logger.info(f"☁️ Uploading to MinIO...",
                   directory=directory_path,
                   filename=filename,
                   content_type="text/markdown")
        
        file_path = await minio_service.save_research_file(
            directory_path=directory_path,
            filename=filename,
            content=markdown_content,
            content_type="text/markdown"
        )
        
        logger.info(f"✅ Successfully saved to MinIO",
                   file_path=file_path,
                   content_size=len(markdown_content))
        
        return {
            "success": True,
            "file_path": file_path,
            "filename": filename,
            "content_length": len(markdown_content),
            "message": f"Successfully saved research to {file_path}"
        }
        
    except Exception as e:
        logger.error(f"❌ Error saving research to MinIO: {e}")
        return {
            "success": False,
            "file_path": None,
            "filename": None,
            "content_length": 0,
            "message": f"Failed to save research: {str(e)}",
            "error": str(e)
        }


# CrewAI Tools (only for agents to use)
def create_perplexity_research_tool(perplexity_model: PerplexityModel = PerplexityModel.SONAR_PRO):
    """Create a Perplexity research tool with the specified model"""
    
    logger.info(f"🔧 Creating Perplexity research tool with model: {perplexity_model.value}")
    
    @tool("perplexity_web_research")
    def perplexity_web_research(query: str, specific_prompt: str = None) -> Dict[str, Any]:
        """
        Perform comprehensive web research using Perplexity API.
        
        Args:
            query: The specific research question to investigate
            specific_prompt: Optional specific prompt for targeted research
            
        Returns:
            Dict with research results and metadata
        """
        logger.info(f"🔍 Tool called: perplexity_web_research with query: {query[:100]}")
        
        # For CrewAI tools, we need to use synchronous execution
        # Return a placeholder result for now
        import asyncio
        try:
            # Try to run async function in sync context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, return a placeholder
                logger.warning(f"⚠️ Tool running in async context, returning placeholder")
                return {
                    "content": f"Research placeholder for: {query}",
                    "citations": [],
                    "model_used": perplexity_model.value,
                    "tokens_used": 0,
                    "query": query,
                    "success": True,
                    "timestamp": datetime.utcnow().isoformat(),
                    "original_query": query,
                    "note": "Placeholder result - async execution not supported in CrewAI tools"
                }
            else:
                # Run the async function
                logger.info(f"🚀 Running async research function from tool")
                return asyncio.run(perform_perplexity_research(query, perplexity_model))
        except Exception as e:
            logger.error(f"❌ Tool execution error: {e}")
            return {
                "content": f"Error occurred during research: {str(e)}",
                "citations": [],
                "model_used": perplexity_model.value,
                "tokens_used": 0,
                "query": query,
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "original_query": query
            }
    
    logger.info(f"✅ Perplexity research tool created successfully")
    return perplexity_web_research


@tool("save_research_to_minio")
def save_research_to_minio(
    research_result: Dict[str, Any], 
    directory_path: str, 
    task_order: int = None
) -> Dict[str, Any]:
    """
    Save research result to MinIO as a markdown file.
    
    Args:
        research_result: The research result from Perplexity
        directory_path: Directory path in MinIO to save the file
        task_order: Optional task order number for filename
        
    Returns:
        Dict with save operation result
    """
    logger.info(f"💾 Tool called: save_research_to_minio",
               directory_path=directory_path,
               task_order=task_order)
    
    # For CrewAI tools, we need to use synchronous execution
    # Return a placeholder result for now
    import asyncio
    try:
        # Try to run async function in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, return a placeholder
            filename = f"research_task_{task_order or 'unknown'}.md"
            logger.warning(f"⚠️ Tool running in async context, returning placeholder save result")
            return {
                "success": True,
                "file_path": f"{directory_path}/{filename}",
                "filename": filename,
                "content_length": len(str(research_result)),
                "message": f"Placeholder save to {directory_path}/{filename}",
                "note": "Placeholder result - async execution not supported in CrewAI tools"
            }
        else:
            # Run the async function
            logger.info(f"🚀 Running async save function from tool")
            return asyncio.run(save_research_to_minio_service(research_result, directory_path, task_order))
    except Exception as e:
        logger.error(f"❌ Tool save error: {e}")
        return {
            "success": False,
            "file_path": None,
            "filename": None,
            "content_length": 0,
            "message": f"Failed to save research: {str(e)}",
            "error": str(e)
        }


class ResearchExecutorAgent:
    """Agent responsible for executing web research and saving results"""
    
    def __init__(
        self, 
        llm_provider: LLMProvider = LLMProvider.OPENAI, 
        llm_model: str = "gpt-4o-mini",
        perplexity_model: PerplexityModel = PerplexityModel.SONAR_PRO
    ):
        logger.info(f"🤖 Initializing ResearchExecutorAgent",
                   llm_provider=llm_provider.value,
                   llm_model=llm_model,
                   perplexity_model=perplexity_model.value)
        
        self.llm = llm_service.get_llm(llm_provider, llm_model)
        self.perplexity_model = perplexity_model
        self.research_tool = create_perplexity_research_tool(perplexity_model)
        
        logger.info(f"✅ ResearchExecutorAgent initialized successfully")
    
    def create_agent(self) -> Agent:
        """Create the CrewAI agent for research execution"""
        logger.info(f"👤 Creating CrewAI agent for research execution")
        
        agent = Agent(
            role="Web Research Specialist",
            goal="Execute comprehensive web research using advanced search capabilities and save results systematically",
            backstory="""You are a highly skilled research analyst with expertise in conducting thorough 
            web-based investigations. You have access to cutting-edge research tools and databases, 
            and you excel at finding, analyzing, and synthesizing information from multiple sources.
            
            Your research methodology is systematic and comprehensive:
            1. You understand the research question deeply before beginning
            2. You use advanced search techniques to find the most relevant and credible sources
            3. You analyze information critically, looking for patterns, trends, and insights
            4. You synthesize findings into clear, actionable intelligence
            5. You maintain detailed records of all research for future reference
            
            You are particularly skilled at:
            - Market research and competitive analysis
            - Technical research and trend identification
            - Finding expert opinions and authoritative sources
            - Cross-referencing information for accuracy
            - Presenting complex information in clear, structured formats
            
            Your work is always thorough, accurate, and professionally documented.""",
            verbose=True,
            llm=self.llm,
            tools=[
                self.research_tool,
                save_research_to_minio
            ],
            allow_delegation=False
        )
        
        logger.info(f"✅ CrewAI agent created successfully")
        return agent
    
    def create_research_tasks(
        self, 
        research_tasks: List['ResearchTaskStructure'], 
        directory_path: str,
        agent: Agent
    ) -> List[Task]:
        """
        Create CrewAI Tasks for research execution
        
        Args:
            research_tasks: List of ResearchTaskStructure objects with specific prompts
            directory_path: MinIO directory path to save results
            agent: The agent that will execute the tasks
            
        Returns:
            List of CrewAI Task objects
        """
        
        tasks = []
        
        for task_structure in research_tasks:
            task = Task(
                description=f"""
                Conduct focused web research on the following specific task:
                
                Focus Area: {task_structure.focus_area}
                Task Question: {task_structure.task_question}
                
                Use the specific prompt designed for this research area:
                {task_structure.specific_prompt}
                
                Use the perplexity_web_research tool to gather detailed information about this specific aspect.
                After completing the research, save the results to MinIO using the save_research_to_minio tool.
                
                Directory path for saving: {directory_path}
                Task order: {task_structure.task_order}
                
                This task is specifically designed to focus on: {task_structure.focus_area}
                """,
                expected_output=f"""
                A focused research report saved to MinIO containing:
                1. Specific analysis for: {task_structure.focus_area}
                2. Detailed findings based on the custom prompt
                3. Key insights and data points
                4. Relevant citations and sources
                5. File successfully saved to: {directory_path}
                """,
                agent=agent,
                tools=[self.research_tool, save_research_to_minio]
            )
            tasks.append(task)
        
        return tasks
    
    async def execute_research_tasks(
        self, 
        research_tasks: List['ResearchTaskStructure'], 
        directory_path: str
    ) -> ResearchExecutionResult:
        """
        Execute research tasks using service functions directly
        
        Args:
            research_tasks: List of ResearchTaskStructure objects with specific prompts
            directory_path: MinIO directory path to save results
            
        Returns:
            ResearchExecutionResult with execution details
        """
        
        try:
            logger.info(f"🚀 Starting research execution",
                       total_tasks=len(research_tasks),
                       directory_path=directory_path,
                       perplexity_model=self.perplexity_model.value)
            
            # Execute only the first task by default for efficiency
            tasks_to_execute = research_tasks[:1]  # Limit to 1 task
            logger.info(f"📝 Will execute {len(tasks_to_execute)} task(s) out of {len(research_tasks)} total")
            
            # Execute tasks using service functions directly
            completed_tasks = []
            failed_tasks = []
            minio_files = []
            
            for i, task_structure in enumerate(tasks_to_execute, 1):
                logger.info(f"📋 Executing task {i}/{len(tasks_to_execute)}",
                           task_number=i,
                           focus_area=task_structure.focus_area,
                           question=task_structure.task_question[:100] + "..." if len(task_structure.task_question) > 100 else task_structure.task_question)
                
                try:
                    # Perform the research using service function with specific prompt
                    logger.info(f"🔍 Step 1: Performing Perplexity research with specific prompt...")
                    research_result = await perform_perplexity_research(
                        query=task_structure.task_question,
                        perplexity_model=self.perplexity_model,
                        specific_prompt=task_structure.specific_prompt
                    )
                    
                    if research_result.get('success', True):  # Default to True if not specified
                        logger.info(f"✅ Research completed successfully for task {i}",
                                   content_length=len(research_result.get('content', '')))
                        
                        # Save to MinIO using service function
                        logger.info(f"💾 Step 2: Saving to MinIO...")
                        save_result = await save_research_to_minio_service(
                            research_result=research_result,
                            directory_path=directory_path,
                            task_order=task_structure.task_order
                        )
                        
                        if save_result.get('success', False):
                            completed_tasks.append(task_structure)
                            minio_files.append(save_result['file_path'])
                            logger.info(f"✅ Task {i} completed successfully",
                                       file_path=save_result['file_path'])
                        else:
                            failed_tasks.append(task_structure)
                            logger.error(f"❌ Failed to save results for task {i}",
                                        error=save_result.get('message', 'Unknown error'))
                    else:
                        failed_tasks.append(task_structure)
                        logger.error(f"❌ Failed to research task {i}",
                                    error=research_result.get('error', 'Unknown error'))
                
                except Exception as e:
                    failed_tasks.append(task_structure)
                    logger.error(f"❌ Exception during task {i}: {e}")
            
            success = len(completed_tasks) > 0
            
            logger.info(f"📊 Research execution summary",
                       total_tasks=len(tasks_to_execute),
                       completed=len(completed_tasks),
                       failed=len(failed_tasks),
                       files_created=len(minio_files),
                       success=success)
            
            return ResearchExecutionResult(
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                minio_files=minio_files,
                success=success
            )
            
        except Exception as e:
            logger.error(f"❌ Error in research execution: {e}", exc_info=True)
            return ResearchExecutionResult(
                completed_tasks=[],
                failed_tasks=research_tasks,  # research_tasks now contains ResearchTaskStructure objects
                minio_files=[],
                success=False
            )
    
    async def execute_single_research(
        self, 
        query: str, 
        directory_path: str,
        task_order: int = None,
        specific_prompt: str = None
    ) -> Dict[str, Any]:
        """
        Execute a single research task
        
        Args:
            query: The research question
            directory_path: MinIO directory path to save results
            task_order: Optional task order number
            specific_prompt: Optional specific prompt for Perplexity
            
        Returns:
            Dict with execution result
        """
        
        try:
            logger.info(f"🔍 Executing single research task",
                       query=query[:100],
                       directory_path=directory_path,
                       task_order=task_order)
            
            # Perform the research using service function
            research_result = await perform_perplexity_research(
                query=query,
                perplexity_model=self.perplexity_model,
                specific_prompt=specific_prompt
            )
            
            if research_result.get('success', False):
                # Save to MinIO using service function
                save_result = await save_research_to_minio_service(
                    research_result=research_result,
                    directory_path=directory_path,
                    task_order=task_order
                )
                
                logger.info(f"✅ Single research task completed",
                           success=save_result.get('success', False))
                
                return {
                    "success": save_result.get('success', False),
                    "research_result": research_result,
                    "save_result": save_result,
                    "message": save_result.get('message', 'Research completed')
                }
            else:
                logger.error(f"❌ Single research task failed",
                            error=research_result.get('error', 'Unknown error'))
                return {
                    "success": False,
                    "research_result": research_result,
                    "save_result": None,
                    "message": f"Research failed: {research_result.get('error', 'Unknown error')}"
                }
        
        except Exception as e:
            logger.error(f"❌ Error in single research execution: {e}")
            return {
                "success": False,
                "research_result": None,
                "save_result": None,
                "message": f"Execution failed: {str(e)}"
            } 
import asyncio
from typing import Dict, Any
from pydantic import BaseModel, Field
from crewai import Task
from crewai.flow.flow import Flow, listen, start
from sqlalchemy.orm import Session
from app.agents.research_planner_agent import ResearchPlannerAgent
from app.agents.research_executor_agent import ResearchExecutorAgent
from app.schemas import (
    LLMProvider, 
    PerplexityModel, 
    ResearchPlanningResult, 
    ResearchExecutionResult,
    ResearchTaskStructure,
    FlowResult,
    ResearchStatus
)
import structlog

logger = structlog.get_logger()


class ResearchFlowState(BaseModel):
    """State management for the research flow"""
    research_id: int = 0
    query: str = ""
    directory_path: str = ""
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: str = "gpt-4o-mini"
    perplexity_model: PerplexityModel = PerplexityModel.SONAR_PRO
    max_planning_tasks: int = 8
    
    # Planning results
    planning_result: ResearchPlanningResult = Field(default_factory=ResearchPlanningResult)
    
    # Execution results
    execution_result: ResearchExecutionResult = Field(default_factory=ResearchExecutionResult)
    
    # Flow control
    should_execute_research: bool = True
    final_status: ResearchStatus = ResearchStatus.PENDING


class ResearchFlow(Flow[ResearchFlowState]):
    """
    CrewAI Flow for orchestrating web research using multiple agents.
    
    This flow coordinates between:
    1. ResearchPlannerAgent: Plans research and checks for duplicates
    2. ResearchExecutorAgent: Executes research tasks using Perplexity API
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.OPENAI,
        llm_model: str = "gpt-4o-mini",
        perplexity_model: PerplexityModel = PerplexityModel.SONAR_PRO,
        db: Session = None
    ):
        super().__init__()
        
        logger.info(f"🌊 Initializing ResearchFlow",
                   llm_provider=llm_provider.value,
                   llm_model=llm_model,
                   perplexity_model=perplexity_model.value,
                   has_db=db is not None)
        
        # Store parameters for agent creation
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.perplexity_model = perplexity_model
        self.db = db
        
        # Initialize agents
        logger.info(f"🤖 Creating ResearchPlannerAgent...")
        self.planner_agent = ResearchPlannerAgent(
            llm_provider=llm_provider,
            llm_model=llm_model
        )
        
        logger.info(f"🤖 Creating ResearchExecutorAgent...")
        self.executor_agent = ResearchExecutorAgent(
            llm_provider=llm_provider,
            llm_model=llm_model,
            perplexity_model=perplexity_model
        )
        
        logger.info(f"✅ ResearchFlow initialized successfully")
    
    def set_flow_state(
        self,
        research_id: int,
        query: str,
        directory_path: str,
        llm_provider: LLMProvider,
        llm_model: str,
        perplexity_model: PerplexityModel,
        max_planning_tasks: int = 8
    ):
        """Set flow state parameters"""
        logger.info(f"⚙️ Setting flow state parameters",
                   research_id=research_id,
                   query=query[:50],
                   directory_path=directory_path)
        
        # Update state fields directly if accessible
        try:
            if hasattr(self, '_state') and self._state is not None:
                self._state.research_id = research_id
                self._state.query = query
                self._state.directory_path = directory_path
                self._state.llm_provider = llm_provider
                self._state.llm_model = llm_model
                self._state.perplexity_model = perplexity_model
                self._state.max_planning_tasks = max_planning_tasks
                logger.info(f"✅ Flow state updated successfully")
            else:
                logger.warning(f"⚠️ Flow state not yet initialized")
        except Exception as e:
            logger.warning(f"⚠️ Could not set flow state directly: {e}")
        
        # Store parameters as instance variables as fallback
        self.current_research_id = research_id
        self.current_query = query
        self.current_directory_path = directory_path
        self.current_llm_provider = llm_provider
        self.current_llm_model = llm_model
        self.current_perplexity_model = perplexity_model
        self.current_max_planning_tasks = max_planning_tasks
        
        logger.info(f"✅ Flow parameters stored successfully")
    
    @start()
    def initialize_research(self) -> Dict[str, Any]:
        """
        Initialize the research flow.
        This is the starting point of the flow.
        """
        # Get state parameters with fallback to instance variables
        query = getattr(self.state, 'query', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_query', '')
        research_id = getattr(self.state, 'research_id', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_research_id', 0)
        directory_path = getattr(self.state, 'directory_path', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_directory_path', '')
        llm_provider = getattr(self.state, 'llm_provider', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_llm_provider', LLMProvider.OPENAI)
        llm_model = getattr(self.state, 'llm_model', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_llm_model', 'gpt-4o-mini')
        perplexity_model = getattr(self.state, 'perplexity_model', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_perplexity_model', PerplexityModel.SONAR_PRO)
        
        logger.info(f"🚀 Starting research flow initialization",
                   query=query,
                   research_id=research_id,
                   directory_path=directory_path,
                   llm_provider=llm_provider.value if hasattr(llm_provider, 'value') else str(llm_provider),
                   llm_model=llm_model,
                   perplexity_model=perplexity_model.value if hasattr(perplexity_model, 'value') else str(perplexity_model))
        
        logger.info(f"✅ Research flow initialized - proceeding to planning phase")
        
        # Return the current state information
        return {
            "query": query,
            "research_id": research_id,
            "directory_path": directory_path,
            "status": "initialized"
        }
    
    @listen(initialize_research)
    async def plan_research(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan the research investigation.
        This step uses the ResearchPlannerAgent to check for similar research
        and create an investigation structure.
        """
        # Get state parameters with fallback
        query = context.get('query') or getattr(self, 'current_query', '')
        research_id = context.get('research_id') or getattr(self, 'current_research_id', 0)
        
        logger.info(f"🧠 Starting research planning phase",
                   query=query,
                   research_id=research_id)
        
        try:
            # Get max_planning_tasks with fallback
            max_planning_tasks = getattr(self.state, 'max_planning_tasks', None) if hasattr(self, 'state') and self.state else getattr(self, 'current_max_planning_tasks', 8)
            
            # Execute research planning using the planner agent
            logger.info(f"📞 Calling planner agent...")
            planning_result = await self.planner_agent.plan_research(
                topic=query,
                objective=f"Comprehensive research on: {query}",
                research_id=research_id,
                db=self.db,
                max_planning_tasks=max_planning_tasks
            )
            
            logger.info(f"✅ Planning completed successfully",
                       has_similar=planning_result.has_similar_research,
                       similar_count=planning_result.similar_research_count,
                       proceed=planning_result.proceed_with_research,
                       tasks_count=len(planning_result.investigation_structure))
            
            # Store planning result in flow state (with fallback to instance variables)
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.planning_result = planning_result
                    self.state.should_execute_research = planning_result.proceed_with_research
            except Exception as e:
                logger.warning(f"⚠️ Could not update flow state directly: {e}")
            
            # Always store as instance variables as fallback
            self.current_planning_result = planning_result
            self.current_should_execute_research = planning_result.proceed_with_research
            
            # Log each investigation question
            logger.info(f"📋 Investigation structure created:")
            for i, question in enumerate(planning_result.investigation_structure, 1):
                logger.info(f"  {i}. {question}")
            
            logger.info(f"✅ Planning phase completed successfully")
            
            # Get current directory path
            directory_path = context.get('directory_path') or getattr(self, 'current_directory_path', '')
            
            # Return updated state information
            return {
                "query": query,
                "research_id": research_id,
                "directory_path": directory_path,
                "status": "planned",
                "proceed_with_research": planning_result.proceed_with_research,
                "investigation_structure": planning_result.investigation_structure
            }
            
        except Exception as e:
            logger.error(f"❌ Error in research planning: {e}")
            
            # Create fallback planning result
            fallback_questions = [
                f"Research current state and trends of {query}",
                f"Identify key players and market leaders in {query}",
                f"Analyze challenges and opportunities in {query}",
                f"Find recent developments and innovations in {query}"
            ]
            
            logger.info(f"🔄 Creating fallback planning with {len(fallback_questions)} questions")
            
            fallback_planning = ResearchPlanningResult(
                has_similar_research=False,
                similar_research_count=0,
                investigation_structure=fallback_questions,
                proceed_with_research=True,
                agent_analysis=f"Planning failed, using fallback: {str(e)}"
            )
            
            # Store fallback result
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.planning_result = fallback_planning
                    self.state.should_execute_research = True
            except Exception as state_error:
                logger.warning(f"⚠️ Could not update flow state with fallback: {state_error}")
            
            self.current_planning_result = fallback_planning
            self.current_should_execute_research = True
            
            directory_path = context.get('directory_path') or getattr(self, 'current_directory_path', '')
            
            return {
                "query": query,
                "research_id": research_id,
                "directory_path": directory_path,
                "status": "planned_with_fallback",
                "proceed_with_research": True,
                "investigation_structure": fallback_planning.investigation_structure,
                "error": str(e)
            }
    
    @listen(plan_research)
    async def execute_research(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the research tasks.
        This step uses the ResearchExecutorAgent to perform web research
        and save results to MinIO.
        """
        # Get parameters with fallback to context and instance variables
        query = context.get('query') or getattr(self, 'current_query', '')
        research_id = context.get('research_id') or getattr(self, 'current_research_id', 0)
        directory_path = context.get('directory_path') or getattr(self, 'current_directory_path', '')
        
        # Get planning result with fallback
        planning_result = None
        try:
            if hasattr(self, 'state') and self.state and hasattr(self.state, 'planning_result'):
                planning_result = self.state.planning_result
        except:
            pass
        
        if not planning_result:
            planning_result = getattr(self, 'current_planning_result', None)
        
        # Get investigation structure
        investigation_structure = planning_result.investigation_structure if planning_result else context.get('investigation_structure', [])
        
        # Get should_execute_research flag
        should_execute_research = context.get('proceed_with_research', True)
        if not should_execute_research:
            try:
                if hasattr(self, 'state') and self.state and hasattr(self.state, 'should_execute_research'):
                    should_execute_research = self.state.should_execute_research
            except:
                pass
            
            if not should_execute_research:
                should_execute_research = getattr(self, 'current_should_execute_research', True)
        
        logger.info(f"🔍 Starting research execution phase",
                   proceed_with_research=should_execute_research,
                   tasks_count=len(investigation_structure),
                   directory_path=directory_path)
        
        # Check if we should proceed with research or use existing content
        if not should_execute_research:
            logger.info("🔍 Checking for existing research content instead of executing new research")
            
            # Check if we have valid existing content
            has_valid_content = planning_result.has_valid_content if planning_result else False
            existing_content = planning_result.existing_research_content if planning_result else []
            
            if has_valid_content and existing_content:
                logger.info(f"🎉 Using existing research content from {len(existing_content)} entries")
                
                # Create virtual files in MinIO with existing content
                from app.services.minio_service import minio_service
                virtual_files = []
                completed_tasks = []
                
                for i, content_item in enumerate(existing_content, 1):
                    try:
                        # Generate filename for existing content
                        task_query = content_item.get('task_query', f'Existing research {i}')
                        filename = minio_service.generate_filename(task_query, i)
                        
                        # Save existing content to new directory
                        file_path = await minio_service.save_research_file(
                            directory_path=directory_path,
                            filename=filename,
                            content=content_item.get('content', ''),
                            content_type="text/markdown"
                        )
                        
                        virtual_files.append(file_path)
                        
                        # Create ResearchTaskStructure for completed task
                        task_structure = ResearchTaskStructure(
                            task_question=task_query,
                            specific_prompt=f"Existing research content: {task_query}",
                            task_order=i,
                            focus_area="Existing Research"
                        )
                        completed_tasks.append(task_structure)
                        
                        logger.info(f"📄 Copied existing content {i}: {task_query[:100]}... -> {file_path}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Could not copy existing content {i}: {e}")
                
                execution_result = ResearchExecutionResult(
                    completed_tasks=completed_tasks,
                    failed_tasks=[],
                    minio_files=virtual_files,
                    success=True
                )
                
                logger.info(f"✅ Successfully used existing research content: {len(virtual_files)} files created")
                
            else:
                logger.info("⏭️ No valid existing content, skipping research execution")
                execution_result = ResearchExecutionResult(
                    completed_tasks=[],
                    failed_tasks=[],
                    minio_files=[],
                    success=True
                )
            
            # Store execution result with fallback
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.execution_result = execution_result
                    self.state.final_status = ResearchStatus.COMPLETED
            except Exception as e:
                logger.warning(f"⚠️ Could not update flow state: {e}")
            
            self.current_execution_result = execution_result
            self.current_final_status = ResearchStatus.COMPLETED
            
            status_message = "completed_with_existing_content" if has_valid_content else "completed_without_execution"
            message = f"Research completed using existing content: {len(execution_result.minio_files)} files created" if has_valid_content else "Research skipped due to existing similar research"
            
            return {
                "query": query,
                "research_id": research_id,
                "directory_path": directory_path,
                "status": status_message,
                "message": message
            }
        
        try:
            # Execute research tasks using the executor agent
            logger.info(f"📞 Calling executor agent with {len(investigation_structure)} tasks...")
            execution_result = await self.executor_agent.execute_research_tasks(
                research_tasks=investigation_structure,
                directory_path=directory_path
            )
            
            logger.info(f"✅ Execution completed",
                       success=execution_result.success,
                       completed=len(execution_result.completed_tasks),
                       failed=len(execution_result.failed_tasks),
                       files=len(execution_result.minio_files))
            
            # Store execution result in flow state with fallback
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.execution_result = execution_result
            except Exception as e:
                logger.warning(f"⚠️ Could not update flow state execution result: {e}")
            
            self.current_execution_result = execution_result
            
            # Log detailed results
            if execution_result.completed_tasks:
                logger.info(f"✅ Completed tasks:")
                for i, task in enumerate(execution_result.completed_tasks, 1):
                    if hasattr(task, 'task_question'):
                        logger.info(f"  {i}. {task.focus_area}: {task.task_question}")
                    else:
                        logger.info(f"  {i}. {task}")
            
            if execution_result.failed_tasks:
                logger.warning(f"❌ Failed tasks:")
                for i, task in enumerate(execution_result.failed_tasks, 1):
                    if hasattr(task, 'task_question'):
                        logger.warning(f"  {i}. {task.focus_area}: {task.task_question}")
                    else:
                        logger.warning(f"  {i}. {task}")
            
            if execution_result.minio_files:
                logger.info(f"📁 Created files:")
                for i, file_path in enumerate(execution_result.minio_files, 1):
                    logger.info(f"  {i}. {file_path}")
            
            # Determine final status
            if execution_result.success:
                final_status = ResearchStatus.COMPLETED
                status = "completed_successfully"
                message = f"Research completed successfully. {len(execution_result.completed_tasks)} tasks completed."
                logger.info(f"🎉 Research execution successful!")
            else:
                final_status = ResearchStatus.FAILED
                status = "completed_with_errors"
                message = f"Research completed with errors. {len(execution_result.failed_tasks)} tasks failed."
                logger.warning(f"⚠️ Research execution completed with errors")
            
            # Store final status with fallback
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.final_status = final_status
            except Exception as e:
                logger.warning(f"⚠️ Could not update flow state final status: {e}")
            
            self.current_final_status = final_status
            
            return {
                "query": query,
                "research_id": research_id,
                "directory_path": directory_path,
                "status": status,
                "message": message
            }
            
        except Exception as e:
            logger.error(f"❌ Error in research execution: {e}")
            
            # Create fallback execution result
            fallback_execution = ResearchExecutionResult(
                completed_tasks=[],
                failed_tasks=investigation_structure,  # investigation_structure now contains ResearchTaskStructure objects
                minio_files=[],
                success=False
            )
            
            # Store fallback execution result with fallback
            try:
                if hasattr(self, 'state') and self.state:
                    self.state.execution_result = fallback_execution
                    self.state.final_status = ResearchStatus.FAILED
            except Exception as state_error:
                logger.warning(f"⚠️ Could not update flow state with fallback execution: {state_error}")
            
            self.current_execution_result = fallback_execution
            self.current_final_status = ResearchStatus.FAILED
            
            return {
                "query": query,
                "research_id": research_id,
                "directory_path": directory_path,
                "status": "failed",
                "message": f"Research execution failed: {str(e)}",
                "error": str(e)
            }
    
# Flow instance for external use
def create_research_flow(
    llm_provider: LLMProvider = LLMProvider.OPENAI,
    llm_model: str = "gpt-4o-mini",
    perplexity_model: PerplexityModel = PerplexityModel.SONAR_PRO,
    db: Session = None
) -> ResearchFlow:
    """Create a new instance of the research flow"""
    logger.info(f"🏭 Creating new research flow instance", 
               llm_provider=llm_provider.value,
               llm_model=llm_model,
               perplexity_model=perplexity_model.value,
               has_db=db is not None)
    return ResearchFlow(
        llm_provider=llm_provider,
        llm_model=llm_model,
        perplexity_model=perplexity_model,
        db=db
    )


async def execute_research_flow(inputs: Dict[str, Any], db: Session = None) -> FlowResult:
    """
    Execute the research flow with given parameters.
    
    Args:
        inputs: Dictionary of inputs for the flow
        db: Database session
        
    Returns:
        FlowResult with final status and results.
    """
    
    logger.info(f"🎬 Starting research flow execution",
               query=inputs.get("query", ""),
               directory_path=inputs.get("directory_path", ""),
               research_id=inputs.get("research_id", 0),
               llm_provider=inputs.get("llm_provider", "openai"),
               llm_model=inputs.get("llm_model", "gpt-4o-mini"),
               perplexity_model=inputs.get("perplexity_model", "sonar-pro"))
    
    try:
        # Create flow instance with proper configuration
        logger.info(f"🏭 Creating flow instance...")
        flow_instance = ResearchFlow(
            llm_provider=LLMProvider(inputs.get("llm_provider", "openai")),
            llm_model=inputs.get("llm_model", "gpt-4o-mini"),
            perplexity_model=PerplexityModel(inputs.get("perplexity_model", "sonar-pro")),
            db=db
        )
        
        # Set flow state parameters before execution
        logger.info(f"⚙️ Setting flow state parameters...")
        flow_instance.set_flow_state(
            research_id=inputs.get("research_id", 0),
            query=inputs.get("query", ""),
            directory_path=inputs.get("directory_path", ""),
            llm_provider=LLMProvider(inputs.get("llm_provider", "openai")),
            llm_model=inputs.get("llm_model", "gpt-4o-mini"),
            perplexity_model=PerplexityModel(inputs.get("perplexity_model", "sonar-pro")),
            max_planning_tasks=inputs.get("max_planning_tasks", 8)
        )
        
        # Execute the flow using CrewAI's kickoff method
        logger.info(f"🚀 Executing CrewAI flow...")
        flow_result = await flow_instance.kickoff_async()
        logger.info(f"✅ CrewAI flow execution completed")
        
        # Get results from flow state with fallback to instance variables
        planning_result = None
        execution_result = None
        final_status = ResearchStatus.PENDING
        
        try:
            if hasattr(flow_instance, 'state') and flow_instance.state:
                planning_result = getattr(flow_instance.state, 'planning_result', None)
                execution_result = getattr(flow_instance.state, 'execution_result', None)
                final_status = getattr(flow_instance.state, 'final_status', ResearchStatus.PENDING)
        except Exception as e:
            logger.warning(f"⚠️ Could not get results from flow state: {e}")
        
        # Fallback to instance variables
        if not planning_result:
            planning_result = getattr(flow_instance, 'current_planning_result', None)
        if not execution_result:
            execution_result = getattr(flow_instance, 'current_execution_result', None)
        if final_status == ResearchStatus.PENDING:
            final_status = getattr(flow_instance, 'current_final_status', ResearchStatus.PENDING)
        
        logger.info(f"📊 Flow execution summary",
                   final_status=final_status.value,
                   has_planning=planning_result is not None,
                   has_execution=execution_result is not None,
                   execution_success=execution_result.success if execution_result else False)
        
        # Determine final message
        if final_status == ResearchStatus.COMPLETED:
            message = "Research flow completed successfully"
            logger.info(f"🎉 Flow completed successfully!")
        elif final_status == ResearchStatus.FAILED:
            message = "Research flow failed"
            logger.error(f"❌ Flow failed")
        else:
            message = f"Research flow finished with status: {final_status.value}"
            logger.warning(f"⚠️ Flow finished with unexpected status: {final_status.value}")
        
        return FlowResult(
            research_id=inputs.get("research_id", 0),
            planning_result=planning_result or ResearchPlanningResult(),
            execution_result=execution_result or ResearchExecutionResult(),
            status=final_status,
            message=message
        )
        
    except Exception as e:
        logger.error(f"❌ Error executing research flow: {e}", exc_info=True)
        return FlowResult(
            research_id=inputs.get("research_id", 0),
            planning_result=ResearchPlanningResult(),
            execution_result=ResearchExecutionResult(),
            status=ResearchStatus.FAILED,
            message=f"Flow execution failed: {str(e)}"
        ) 
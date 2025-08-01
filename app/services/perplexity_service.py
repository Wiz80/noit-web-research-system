import httpx
import asyncio
from typing import Dict, Any, Optional
from app.config import settings
from app.schemas import PerplexityModel
import structlog

logger = structlog.get_logger()


class PerplexityService:
    """Service for interacting with Perplexity API"""
    
    def __init__(self):
        self.api_key = settings.perplexity_api_key
        self.base_url = "https://api.perplexity.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def clean_perplexity_content(self, content: str) -> str:
        """
        Clean Perplexity response content by removing <think> </think> tags and other unwanted elements
        
        Args:
            content: Raw content from Perplexity API
            
        Returns:
            Cleaned content without thinking tags
        """
        if not content:
            return content
        
        import re
        
        # Remove <think> ... </think> blocks (case insensitive, multiline)
        # This regex handles both single line and multiline think blocks
        cleaned_content = re.sub(
            r'<think>.*?</think>', 
            '', 
            content, 
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Remove any standalone <think> or </think> tags that might be left
        cleaned_content = re.sub(r'</?think>', '', cleaned_content, flags=re.IGNORECASE)
        
        # Clean up extra whitespace and line breaks that might be left
        cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)  # Remove triple+ line breaks
        cleaned_content = cleaned_content.strip()
        
        # Log the cleaning operation if think tags were found
        if '<think>' in content.lower() or '</think>' in content.lower():
            original_length = len(content)
            cleaned_length = len(cleaned_content)
            removed_chars = original_length - cleaned_length
            
            logger.info(f"🧹 Cleaned Perplexity response content",
                       original_length=original_length,
                       cleaned_length=cleaned_length,
                       removed_chars=removed_chars,
                       had_think_tags=True)
        
        return cleaned_content

    async def search_and_research(
        self, 
        query: str, 
        model: PerplexityModel = PerplexityModel.SONAR_PRO,
        max_tokens: int = 4000,
        temperature: float = 0.1
    ) -> Dict[str, Any]:
        """
        Perform web research using Perplexity API
        
        Args:
            query: Research question or topic
            model: Perplexity model to use
            max_tokens: Maximum tokens in response
            temperature: Response randomness (0.0-1.0)
            
        Returns:
            Dict containing the research result and metadata
        """
        
        logger.info(f"🔍 Starting Perplexity search_and_research",
                   model=model.value,
                   query_length=len(query),
                   max_tokens=max_tokens,
                   temperature=temperature,
                   has_api_key=bool(self.api_key))
        
        if not self.api_key:
            error_msg = "Perplexity API key not configured"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        payload = {
            "model": model.value,
            "messages": [
                {
                    "role": "system",
                    "content": """You are a professional research assistant. Provide comprehensive, well-structured research on the given topic. 
                    Include:
                    1. Key findings and insights
                    2. Recent developments and trends
                    3. Relevant statistics and data
                    4. Multiple perspectives on the topic
                    5. Credible sources and references
                    
                    Format your response in clear markdown with headers, bullet points, and proper citations."""
                },
                {
                    "role": "user", 
                    "content": query
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "return_citations": True,
            "return_images": False
        }
        
        logger.info(f"📝 Perplexity API payload prepared",
                   messages_count=len(payload["messages"]),
                   system_content_length=len(payload["messages"][0]["content"]),
                   user_content_length=len(payload["messages"][1]["content"]))
        
        async with httpx.AsyncClient(timeout=800.0) as client:
            try:
                logger.info(f"🌐 Making Perplexity API request with 800s timeout...",
                           model=model.value,
                           query_length=len(query),
                           max_tokens=max_tokens,
                           url=f"{self.base_url}/chat/completions")
                
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                )
                
                logger.info(f"✅ Perplexity API response received",
                           status_code=response.status_code,
                           response_size=len(response.text),
                           content_type=response.headers.get('content-type', 'unknown'))
                
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"📊 Perplexity API response parsed",
                           response_keys=list(data.keys()),
                           choices_count=len(data.get("choices", [])),
                           has_usage=bool(data.get("usage")),
                           has_citations=bool(data.get("citations")))
                
                # Extract the main content
                choices = data.get("choices", [])
                if not choices:
                    error_msg = "No choices in Perplexity API response"
                    logger.error(f"❌ {error_msg}", data_keys=list(data.keys()))
                    return {
                        "content": "",
                        "citations": [],
                        "model_used": model.value,
                        "tokens_used": 0,
                        "query": query,
                        "success": False,
                        "error": error_msg
                    }
                
                message = choices[0].get("message", {})
                content = message.get("content", "")
                
                logger.info(f"📝 Content extracted from response",
                           content_length=len(content),
                           has_content=bool(content.strip()),
                           message_keys=list(message.keys()))
                
                # Clean the content to remove <think> tags and other unwanted elements
                if content:
                    logger.info(f"🧹 Cleaning Perplexity response content...")
                    content = self.clean_perplexity_content(content)
                    logger.info(f"✅ Content cleaning completed",
                               final_content_length=len(content),
                               has_cleaned_content=bool(content.strip()))
                
                # Extract citations if available
                citations = data.get("citations", [])
                
                # Check if we got valid content after cleaning
                if not content or not content.strip():
                    error_msg = "Empty content received from Perplexity API (after cleaning)"
                    logger.error(f"❌ {error_msg}",
                               raw_content=repr(content),
                               message_content=message.get("content"),
                               choices_data=choices[0])
                    return {
                        "content": "",
                        "citations": citations,
                        "model_used": model.value,
                        "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                        "query": query,
                        "success": False,
                        "error": error_msg
                    }
                
                result = {
                    "content": content,
                    "citations": citations,
                    "model_used": model.value,
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                    "query": query,
                    "success": True
                }
                
                logger.info(f"✅ Perplexity research completed successfully",
                           final_content_length=len(content),  # This is now the cleaned content length
                           citations_count=len(citations),
                           tokens_used=result["tokens_used"],
                           content_cleaned=True)
                
                return result
                
            except httpx.TimeoutException as e:
                error_detail = f"Request timeout after 800 seconds: {str(e)}"
                logger.error(f"⏰ Perplexity API timeout", error=error_detail)
                return {
                    "content": "",
                    "citations": [],
                    "model_used": model.value,
                    "tokens_used": 0,
                    "query": query,
                    "success": False,
                    "error": error_detail
                }
            except httpx.HTTPStatusError as e:
                error_detail = f"HTTP {e.response.status_code}: {e.response.text}"
                logger.error(f"❌ Perplexity API HTTP error", error=error_detail, status_code=e.response.status_code)
                return {
                    "content": "",
                    "citations": [],
                    "model_used": model.value,
                    "tokens_used": 0,
                    "query": query,
                    "success": False,
                    "error": error_detail
                }
            except Exception as e:
                error_detail = str(e)
                logger.error(f"❌ Perplexity API unexpected error", error=error_detail)
                return {
                    "content": "",
                    "citations": [],
                    "model_used": model.value,
                    "tokens_used": 0,
                    "query": query,
                    "success": False,
                    "error": error_detail
                }
    
    async def batch_research(
        self, 
        queries: list[str], 
        model: PerplexityModel = PerplexityModel.SONAR_PRO,
        max_concurrent: int = 3
    ) -> list[Dict[str, Any]]:
        """
        Perform multiple research queries concurrently
        
        Args:
            queries: List of research questions
            model: Perplexity model to use
            max_concurrent: Maximum concurrent requests
            
        Returns:
            List of research results
        """
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def research_with_semaphore(query: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.search_and_research(query, model)
        
        tasks = [research_with_semaphore(query) for query in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "content": "",
                    "citations": [],
                    "model_used": model.value,
                    "tokens_used": 0,
                    "query": queries[i],
                    "success": False,
                    "error": str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_available_models(self) -> list[str]:
        """Get list of available Perplexity models"""
        return [model.value for model in PerplexityModel]
    
    def format_research_as_markdown(self, research_result: Dict[str, Any]) -> str:
        """
        Format research result as markdown for saving to file.
        This now only returns the raw content from the research.
        
        Args:
            research_result: Result from search_and_research method
            
        Returns:
            Formatted markdown string (now just the content)
        """
        
        if not research_result.get("success", False):
            return f"""# Research Failed

**Query**: {research_result.get('query', 'Unknown')}
**Error**: {research_result.get('error', 'Unknown')}
**Model Used**: {research_result.get('model_used', 'Unknown')}
"""
        
        # Return only the content part of the research
        return research_result.get('content', '')


# Global Perplexity service instance
perplexity_service = PerplexityService() 
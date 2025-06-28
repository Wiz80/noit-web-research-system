import httpx
import asyncio
from typing import Dict, Any, Optional
from app.config import settings
from app.schemas import PerplexityModel


class PerplexityService:
    """Service for interacting with Perplexity API"""
    
    def __init__(self):
        self.api_key = settings.perplexity_api_key
        self.base_url = "https://api.perplexity.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
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
        
        if not self.api_key:
            raise ValueError("Perplexity API key not configured")
        
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
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract the main content
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Extract citations if available
                citations = data.get("citations", [])
                
                return {
                    "content": content,
                    "citations": citations,
                    "model_used": model.value,
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0),
                    "query": query,
                    "success": True
                }
                
            except httpx.HTTPStatusError as e:
                error_detail = f"HTTP {e.response.status_code}: {e.response.text}"
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
                return {
                    "content": "",
                    "citations": [],
                    "model_used": model.value,
                    "tokens_used": 0,
                    "query": query,
                    "success": False,
                    "error": str(e)
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
        Format research result as markdown for saving to file
        
        Args:
            research_result: Result from search_and_research method
            
        Returns:
            Formatted markdown string
        """
        
        if not research_result.get("success", False):
            return f"""# Research Failed

**Query**: {research_result.get('query', 'Unknown')}

**Error**: {research_result.get('error', 'Unknown error')}

**Model Used**: {research_result.get('model_used', 'Unknown')}

**Timestamp**: {research_result.get('timestamp', 'Unknown')}
"""
        
        markdown_content = f"""# Research Report

**Query**: {research_result['query']}

**Model Used**: {research_result['model_used']}

**Tokens Used**: {research_result.get('tokens_used', 0)}

---

## Research Results

{research_result['content']}

---

## Citations and Sources

"""
        
        # Add citations if available
        citations = research_result.get('citations', [])
        if citations:
            for i, citation in enumerate(citations, 1):
                if isinstance(citation, dict):
                    title = citation.get('title', 'Unknown Title')
                    url = citation.get('url', '#')
                    markdown_content += f"{i}. [{title}]({url})\n"
                else:
                    markdown_content += f"{i}. {citation}\n"
        else:
            markdown_content += "No specific citations provided.\n"
        
        markdown_content += f"\n---\n\n**Research completed using Perplexity AI ({research_result['model_used']})**"
        
        return markdown_content


# Global Perplexity service instance
perplexity_service = PerplexityService() 
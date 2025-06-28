from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.language_models import BaseLanguageModel
from app.config import settings
from app.schemas import LLMProvider


class LLMService:
    """Service for managing different LLM providers"""
    
    def __init__(self):
        self._models = {}
    
    def get_llm(self, provider: LLMProvider, model: str = None) -> BaseLanguageModel:
        """Get LLM instance based on provider and model"""
        
        cache_key = f"{provider.value}:{model or 'default'}"
        
        if cache_key in self._models:
            return self._models[cache_key]
        
        llm = self._create_llm(provider, model)
        self._models[cache_key] = llm
        return llm
    
    def _create_llm(self, provider: LLMProvider, model: str = None) -> BaseLanguageModel:
        """Create LLM instance based on provider"""
        
        if provider == LLMProvider.OPENAI:
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key not configured")
            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model=model or "gpt-4o-mini",
                temperature=0.1
            )
        
        elif provider == LLMProvider.ANTHROPIC:
            if not settings.anthropic_api_key:
                raise ValueError("Anthropic API key not configured")
            return ChatAnthropic(
                api_key=settings.anthropic_api_key,
                model=model or "claude-3-haiku-20240307",
                temperature=0.1
            )
        
        elif provider == LLMProvider.GOOGLE:
            if not settings.google_api_key:
                raise ValueError("Google API key not configured")
            return ChatGoogleGenerativeAI(
                google_api_key=settings.google_api_key,
                model=model or "gemini-1.5-flash",
                temperature=0.1
            )
        
        elif provider == LLMProvider.DEEPSEEK:
            if not settings.deepseek_api_key:
                raise ValueError("DeepSeek API key not configured")
            return ChatDeepSeek(
                api_key=settings.deepseek_api_key,
                model=model or "deepseek-chat",
                temperature=0.1
            )
        
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    def get_available_models(self, provider: LLMProvider) -> list[str]:
        """Get list of available models for a provider"""
        
        model_mapping = {
            LLMProvider.OPENAI: [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-3.5-turbo"
            ],
            LLMProvider.ANTHROPIC: [
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229",
                "claude-3-opus-20240229"
            ],
            LLMProvider.GOOGLE: [
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-pro"
            ],
            LLMProvider.DEEPSEEK: [
                "deepseek-chat",
                "deepseek-coder"
            ]
        }
        
        return model_mapping.get(provider, [])


# Global LLM service instance
llm_service = LLMService() 
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseLLMProvider(ABC):
    """
    Abstract base interface for text LLM completion providers in S2V.
    """
    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Executes a completion request and returns the structured dictionary response.
        """
        pass

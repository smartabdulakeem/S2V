import json
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

    def complete_text(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048
    ) -> str:
        """
        Executes a plain text completion request and returns the raw string response.
        Default implementation delegates to complete() if returning structured data,
        or subclasses override for direct text endpoints.
        """
        res = self.complete(system=system, user=user, max_tokens=max_tokens)
        if isinstance(res, dict):
            return str(res.get("text") or res.get("content") or json.dumps(res))
        return str(res)


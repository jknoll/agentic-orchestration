"""Ad Generator - Generate video advertisements from product pages."""

from .agent import AdGeneratorAgent
from .agentql_client import AgentQLClient, AgentQLError
from .freepik_client import FreePikClient, FreePikError
from .models import (
    AdScene,
    AdScript,
    GenerationOutput,
    MarketingAnalysis,
    ProductMetadata,
    ProductResearch,
    ResearchOutput,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoResolution,
    VideoStatus,
)
from .research_agent import ResearchAgent

__version__ = "0.1.0"

__all__ = [
    "AdGeneratorAgent",
    "AdScene",
    "AdScript",
    "AgentQLClient",
    "AgentQLError",
    "FreePikClient",
    "FreePikError",
    "GenerationOutput",
    "MarketingAnalysis",
    "ProductMetadata",
    "ProductResearch",
    "ResearchAgent",
    "ResearchOutput",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "VideoResolution",
    "VideoStatus",
]

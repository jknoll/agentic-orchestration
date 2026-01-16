"""Tests for the research agent and AgentQL client."""

import pytest
import respx
from httpx import Response

from ad_generator.agentql_client import AgentQLClient, AgentQLError
from ad_generator.models import ProductResearch, MarketingAnalysis, ResearchOutput


MOCK_RESPONSE = {
    "data": {
        "product_name": "Test Product",
        "price": "$99.99",
        "description": "A great product",
        "features": ["Feature 1", "Feature 2"],
        "specifications": ["Spec 1"],
        "benefits": ["Benefit 1"],
        "target_audience": "Tech enthusiasts",
        "images": ["https://example.com/img.jpg"],
    }
}


class TestAgentQLClient:
    """Tests for AgentQLClient."""

    def test_init_with_api_key(self):
        """Test client initialization with explicit API key."""
        client = AgentQLClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_init_without_api_key_raises(self, monkeypatch):
        """Test client raises error when no API key is provided."""
        monkeypatch.delenv("AGENTQL_API_KEY", raising=False)
        with pytest.raises(AgentQLError, match="API key not provided"):
            AgentQLClient()

    def test_init_from_env(self, monkeypatch):
        """Test client reads API key from environment."""
        monkeypatch.setenv("AGENTQL_API_KEY", "env-test-key")
        client = AgentQLClient()
        assert client.api_key == "env-test-key"

    def test_build_query(self):
        """Test query building from field list."""
        client = AgentQLClient(api_key="test-key")
        query = client._build_query(["product_name", "price", "features"])
        assert "product_name" in query
        assert "price" in query
        assert "features[]" in query  # Array fields get [] suffix

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_success(self):
        """Test successful product extraction."""
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(200, json=MOCK_RESPONSE)
        )

        async with AgentQLClient(api_key="test-key") as client:
            result = await client.extract_product("https://example.com/product")

        assert result.product_name == "Test Product"
        assert result.price == "$99.99"
        assert result.description == "A great product"
        assert len(result.features) == 2
        assert result.features[0] == "Feature 1"
        assert len(result.specifications) == 1
        assert len(result.benefits) == 1
        assert result.target_audience == "Tech enthusiasts"
        assert len(result.images) == 1
        assert result.url == "https://example.com/product"

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_with_custom_fields(self):
        """Test extraction with custom fields."""
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(200, json=MOCK_RESPONSE)
        )

        async with AgentQLClient(api_key="test-key") as client:
            result = await client.extract_product(
                "https://example.com/product",
                fields=["product_name", "price"],
            )

        assert result.product_name == "Test Product"
        assert result.price == "$99.99"

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_api_error(self):
        """Test API error handling."""
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(401, text="Unauthorized")
        )

        async with AgentQLClient(api_key="bad-key") as client:
            with pytest.raises(AgentQLError) as exc:
                await client.extract_product("https://example.com/product")
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_product_server_error(self):
        """Test server error handling."""
        respx.post("https://api.agentql.com/v1/query-data").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        async with AgentQLClient(api_key="test-key") as client:
            with pytest.raises(AgentQLError) as exc:
                await client.extract_product("https://example.com/product")
            assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_client_not_initialized_error(self):
        """Test error when using client outside context manager."""
        client = AgentQLClient(api_key="test-key")
        with pytest.raises(AgentQLError, match="Client not initialized"):
            await client.extract_product("https://example.com/product")


class TestProductResearch:
    """Tests for ProductResearch model."""

    def test_create_minimal(self):
        """Test creating ProductResearch with minimal fields."""
        research = ProductResearch(url="https://example.com/product")
        assert research.url == "https://example.com/product"
        assert research.product_name is None
        assert research.features == []

    def test_create_full(self):
        """Test creating ProductResearch with all fields."""
        research = ProductResearch(
            product_name="Test Product",
            price="$99.99",
            description="A great product",
            features=["Feature 1", "Feature 2"],
            specifications=["Spec 1"],
            benefits=["Benefit 1"],
            target_audience="Tech enthusiasts",
            images=["https://example.com/img.jpg"],
            url="https://example.com/product",
        )
        assert research.product_name == "Test Product"
        assert research.price == "$99.99"
        assert len(research.features) == 2

    def test_model_dump(self):
        """Test model serialization."""
        research = ProductResearch(
            product_name="Test",
            url="https://example.com",
        )
        data = research.model_dump()
        assert data["product_name"] == "Test"
        assert data["url"] == "https://example.com"


class TestMarketingAnalysis:
    """Tests for MarketingAnalysis model."""

    def test_create_minimal(self):
        """Test creating MarketingAnalysis with defaults."""
        analysis = MarketingAnalysis()
        assert analysis.key_features == []
        assert analysis.target_audience_description == ""
        assert analysis.marketing_hooks == {}

    def test_create_full(self):
        """Test creating MarketingAnalysis with all fields."""
        analysis = MarketingAnalysis(
            key_features=["Fast", "Reliable"],
            target_audience_description="Young professionals",
            pain_points_addressed=["Time savings"],
            unique_selling_propositions=["Best in class"],
            marketing_hooks={
                "emotional": "Feel confident",
                "rational": "Save 2 hours per day",
                "social": "Join 1M+ users",
            },
        )
        assert len(analysis.key_features) == 2
        assert len(analysis.marketing_hooks) == 3


class TestResearchOutput:
    """Tests for ResearchOutput model."""

    def test_create_minimal(self):
        """Test creating ResearchOutput with minimal fields."""
        product = ProductResearch(url="https://example.com")
        output = ResearchOutput(product=product)
        assert output.product.url == "https://example.com"
        assert output.analysis is None
        assert output.raw_response is None

    def test_create_full(self):
        """Test creating ResearchOutput with all fields."""
        product = ProductResearch(
            product_name="Test",
            url="https://example.com",
        )
        analysis = MarketingAnalysis(
            key_features=["Feature 1"],
        )
        output = ResearchOutput(
            product=product,
            analysis=analysis,
            raw_response="## Analysis\nTest product analysis",
        )
        assert output.product.product_name == "Test"
        assert output.analysis.key_features == ["Feature 1"]
        assert "Analysis" in output.raw_response

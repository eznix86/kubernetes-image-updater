"""Basic tests for ImageRegistry service."""

from controller import ImageRegistry


class TestImageRegistryBasic:
    """Basic tests for ImageRegistry without complex mocking."""

    def test_init(self):
        """Test ImageRegistry initialization."""
        registry = ImageRegistry()
        assert registry.timeout == 10
        assert hasattr(registry, "session")

    def test_init_custom_timeout(self):
        """Test ImageRegistry initialization with custom timeout."""
        registry = ImageRegistry(timeout=30)
        assert registry.timeout == 30

    def test_parse_auth_header_bearer(self):
        """Test parsing Bearer authentication header."""
        registry = ImageRegistry()
        header = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:nginx:pull"'
        params = registry._parse_auth_header(header)

        assert params == {
            "realm": "https://auth.docker.io/token",
            "service": "registry.docker.io",
            "scope": "repository:nginx:pull",
        }

    def test_parse_auth_header_non_bearer(self):
        """Test parsing non-Bearer authentication header."""
        registry = ImageRegistry()
        header = 'Basic realm="Registry Realm"'
        params = registry._parse_auth_header(header)

        assert params == {}

    def test_parse_auth_header_none(self):
        """Test parsing None authentication header."""
        registry = ImageRegistry()
        params = registry._parse_auth_header(None)

        assert params == {}

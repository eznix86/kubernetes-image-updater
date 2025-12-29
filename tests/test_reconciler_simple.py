"""Simplified integration tests for ImageUpdateReconciler."""

import pytest
from unittest.mock import Mock
from controller import (
    ContainerInfo,
    WorkloadKind,
    ImageUpdateReconciler,
    ImageRegistry,
    WorkloadManager,
    ContainerSelector,
)


class TestImageUpdateReconcilerSimplified:
    """Simplified tests for ImageUpdateReconciler focusing on core logic."""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        return Mock()

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry."""
        return Mock(spec=ImageRegistry)

    @pytest.fixture
    def mock_workload_manager(self):
        """Create mock workload manager."""
        return Mock(spec=WorkloadManager)

    @pytest.fixture
    def mock_container_selector(self):
        """Create mock container selector."""
        return Mock(spec=ContainerSelector)

    @pytest.fixture
    def reconciler(
        self, mock_registry, mock_workload_manager, mock_container_selector, mock_logger
    ):
        """Create reconciler with mocked dependencies."""
        return ImageUpdateReconciler(
            registry=mock_registry,
            workload_manager=mock_workload_manager,
            container_selector=mock_container_selector,
            logger=mock_logger,
        )

    def test_parse_containers(self, reconciler):
        """Test parsing containers from spec."""
        container_list = [
            {"name": "nginx", "image": "nginx:latest", "imagePullPolicy": "Always"},
            {"name": "sidecar", "image": "myapp:v1"},
            {"invalid": "container"},  # Missing name/image
        ]

        containers = reconciler._parse_containers(container_list)

        assert len(containers) == 2
        assert containers[0].name == "nginx"
        assert containers[0].image == "nginx:latest"
        assert containers[0].image_pull_policy == "Always"
        assert containers[1].name == "sidecar"
        assert containers[1].image == "myapp:v1"
        assert containers[1].image_pull_policy is None

    def test_fetch_digests_all_success(self, reconciler, mock_registry):
        """Test successful digest fetching for all containers."""
        containers = [
            ContainerInfo(name="nginx", image="nginx:latest"),
            ContainerInfo(name="sidecar", image="myapp:v1"),
        ]

        mock_registry.get_digest.side_effect = ["sha256:nginx", "sha256:sidecar"]

        result = reconciler._fetch_digests(
            containers, WorkloadKind.DEPLOYMENT, "test", "default"
        )

        assert result is not None
        assert result.digests == {"nginx": "sha256:nginx", "sidecar": "sha256:sidecar"}
        assert mock_registry.get_digest.call_count == 2

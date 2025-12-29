"""Tests for ContainerSelector service."""

import pytest
from controller import Config, ContainerInfo, ContainerSelector


class TestContainerSelector:
    """Test ContainerSelector functionality."""

    @pytest.fixture
    def sample_containers(self):
        """Create sample containers for testing."""
        return [
            ContainerInfo(name="nginx", image="nginx:latest"),
            ContainerInfo(name="sidecar", image="myapp/sidecar:v1.0"),
            ContainerInfo(name="log-collector", image="fluentd:v1.16"),
            ContainerInfo(name="metrics-exporter", image="prometheus:v2.0"),
        ]

    def test_select_all_containers_default(self, sample_containers):
        """Test selecting all containers by default."""
        selected = ContainerSelector.select(sample_containers, {})
        assert len(selected) == 4
        assert selected == sample_containers

    def test_select_track_containers(self, sample_containers):
        """Test selecting specific containers to track."""
        annotations = {Config.TRACK_CONTAINERS_ANNOTATION: "nginx,sidecar"}
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 2
        selected_names = {c.name for c in selected}
        assert selected_names == {"nginx", "sidecar"}

    def test_select_track_containers_whitespace_handling(self, sample_containers):
        """Test that whitespace in track-containers is handled properly."""
        annotations = {Config.TRACK_CONTAINERS_ANNOTATION: " nginx , sidecar "}
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 2
        selected_names = {c.name for c in selected}
        assert selected_names == {"nginx", "sidecar"}

    def test_select_track_containers_empty_entries(self, sample_containers):
        """Test handling of empty entries in track-containers."""
        annotations = {Config.TRACK_CONTAINERS_ANNOTATION: "nginx,,sidecar,"}
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 2
        selected_names = {c.name for c in selected}
        assert selected_names == {"nginx", "sidecar"}

    def test_select_ignore_containers(self, sample_containers):
        """Test ignoring specific containers."""
        annotations = {
            Config.IGNORE_CONTAINERS_ANNOTATION: "log-collector,metrics-exporter"
        }
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 2
        selected_names = {c.name for c in selected}
        assert selected_names == {"nginx", "sidecar"}

    def test_select_ignore_containers_whitespace_handling(self, sample_containers):
        """Test that whitespace in ignore-containers is handled properly."""
        annotations = {
            Config.IGNORE_CONTAINERS_ANNOTATION: " log-collector , metrics-exporter "
        }
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 2
        selected_names = {c.name for c in selected}
        assert selected_names == {"nginx", "sidecar"}

    def test_track_containers_takes_precedence_over_ignore(self, sample_containers):
        """Test that track-containers takes precedence over ignore-containers."""
        annotations = {
            Config.TRACK_CONTAINERS_ANNOTATION: "nginx",
            Config.IGNORE_CONTAINERS_ANNOTATION: "nginx",  # This should be ignored
        }
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 1
        assert selected[0].name == "nginx"

    def test_select_empty_result(self, sample_containers):
        """Test selecting containers that don't exist."""
        annotations = {Config.TRACK_CONTAINERS_ANNOTATION: "nonexistent"}
        selected = ContainerSelector.select(sample_containers, annotations)

        assert len(selected) == 0

    def test_select_with_none_annotations(self):
        """Test selecting with None annotations."""
        containers = [ContainerInfo(name="test", image="test:latest")]
        selected = ContainerSelector.select(containers, None)
        assert len(selected) == 1
        assert selected[0].name == "test"

    def test_select_empty_containers(self):
        """Test selecting from empty container list."""
        selected = ContainerSelector.select([], {})
        assert len(selected) == 0

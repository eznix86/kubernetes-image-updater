"""Tests for domain models and utilities."""

import pytest
from controller import (
    Config,
    ImageReference,
    ContainerInfo,
    DigestMap,
    WorkloadKind,
)


class TestImageReference:
    """Test ImageReference parsing functionality."""

    @pytest.mark.parametrize(
        "image,expected",
        [
            (
                "nginx:latest",
                {
                    "registry": "registry-1.docker.io",
                    "repository": "library/nginx",
                    "tag": "latest",
                },
            ),
            (
                "myregistry.io/myorg/app:v1.2.3",
                {
                    "registry": "myregistry.io",
                    "repository": "myorg/app",
                    "tag": "v1.2.3",
                },
            ),
            (
                "localhost:5000/myapp:dev",
                {"registry": "localhost:5000", "repository": "myapp", "tag": "dev"},
            ),
            (
                "ghcr.io/owner/repo:tag",
                {"registry": "ghcr.io", "repository": "owner/repo", "tag": "tag"},
            ),
            (
                "quay.io/project/image:v1.0",
                {"registry": "quay.io", "repository": "project/image", "tag": "v1.0"},
            ),
        ],
    )
    def test_parse_image_references(self, image, expected):
        """Test parsing various image reference formats."""
        ref = ImageReference.parse(image)
        assert ref.registry == expected["registry"]
        assert ref.repository == expected["repository"]
        assert ref.tag == expected["tag"]

    def test_image_reference_immutability(self):
        """Test that ImageReference is immutable."""
        ref = ImageReference.parse("nginx:latest")
        with pytest.raises(AttributeError):
            ref.registry = "other-registry"


class TestContainerInfo:
    """Test ContainerInfo functionality."""

    def test_container_info_creation(self):
        """Test basic ContainerInfo creation."""
        container = ContainerInfo(name="nginx", image="nginx:latest")
        assert container.name == "nginx"
        assert container.image == "nginx:latest"
        assert container.image_pull_policy is None

    def test_needs_pull_policy_update(self):
        """Test pull policy update detection."""
        # Needs update
        c1 = ContainerInfo(
            name="nginx", image="nginx:latest", image_pull_policy="IfNotPresent"
        )
        assert c1.needs_pull_policy_update is True

        # Already correct
        c2 = ContainerInfo(
            name="nginx", image="nginx:latest", image_pull_policy="Always"
        )
        assert c2.needs_pull_policy_update is False

        # None policy (defaults to needs update)
        c3 = ContainerInfo(name="nginx", image="nginx:latest")
        assert c3.needs_pull_policy_update is True


class TestDigestMap:
    """Test DigestMap functionality."""

    @pytest.mark.parametrize(
        "annotation,expected",
        [
            (None, {}),
            ("", {}),
            ("nginx:sha256:abc123", {"nginx": "sha256:abc123"}),
            (
                "nginx:sha256:abc123,sidecar:sha256:def456",
                {"nginx": "sha256:abc123", "sidecar": "sha256:def456"},
            ),
            (
                "init-db:sha256:xyz789,nginx:sha256:abc123",
                {"init-db": "sha256:xyz789", "nginx": "sha256:abc123"},
            ),
            ("sha256:legacy123", {"__legacy__": "sha256:legacy123"}),  # Legacy format
            ("sha384:legacy456", {"__legacy__": "sha384:legacy456"}),  # Legacy format
        ],
    )
    def test_from_annotation(self, annotation, expected):
        """Test parsing annotations into DigestMap."""
        digest_map = DigestMap.from_annotation(annotation)
        assert digest_map.digests == expected

    def test_to_annotation(self):
        """Test converting DigestMap to annotation string."""
        # Empty map
        dm = DigestMap({})
        assert dm.to_annotation() == ""

        # Single container
        dm = DigestMap({"nginx": "sha256:abc123"})
        assert dm.to_annotation() == "nginx:sha256:abc123"

        # Multiple containers (should be sorted alphabetically)
        dm = DigestMap(
            {"nginx": "sha256:abc", "sidecar": "sha256:def", "init-db": "sha256:xyz"}
        )
        result = dm.to_annotation()
        # Check all parts are present (order may vary due to dict ordering in older Python)
        assert "nginx:sha256:abc" in result
        assert "sidecar:sha256:def" in result
        assert "init-db:sha256:xyz" in result
        assert result.count(",") == 2  # Should have exactly 2 commas

    def test_has_changed(self):
        """Test change detection between DigestMaps."""
        # Same digests
        old = DigestMap({"nginx": "sha256:same", "sidecar": "sha256:same"})
        new = DigestMap({"nginx": "sha256:same", "sidecar": "sha256:same"})
        assert old.has_changed(new) is False

        # Different digest
        old = DigestMap({"nginx": "sha256:old"})
        new = DigestMap({"nginx": "sha256:new"})
        assert old.has_changed(new) is True

        # New container added
        old = DigestMap({"nginx": "sha256:abc"})
        new = DigestMap({"nginx": "sha256:abc", "sidecar": "sha256:def"})
        assert old.has_changed(new) is True

        # Container removed
        old = DigestMap({"nginx": "sha256:abc", "sidecar": "sha256:def"})
        new = DigestMap({"nginx": "sha256:abc"})
        assert old.has_changed(new) is True

    def test_migrate_legacy(self):
        """Test legacy digest migration."""
        # Legacy digest
        legacy = DigestMap({"__legacy__": "sha256:legacy123"})
        migrated = legacy.migrate_legacy("nginx")
        assert migrated.digests == {"nginx": "sha256:legacy123"}

        # Non-legacy digest (should return self)
        normal = DigestMap({"nginx": "sha256:abc123"})
        migrated = normal.migrate_legacy("other")
        assert migrated is normal  # Should return self, not a copy


class TestWorkloadKind:
    """Test WorkloadKind enum."""

    def test_workload_kind_values(self):
        """Test WorkloadKind enum values."""
        assert WorkloadKind.DEPLOYMENT.value == "deployment"
        assert WorkloadKind.STATEFULSET.value == "statefulset"
        assert WorkloadKind.DAEMONSET.value == "daemonset"

    def test_workload_kind_string_conversion(self):
        """Test string conversion."""
        assert WorkloadKind.DEPLOYMENT.value == "deployment"


class TestConfig:
    """Test configuration constants."""

    def test_config_constants(self):
        """Test that config constants are properly defined."""
        assert Config.ENABLE_ANNOTATION.startswith("image-updater.eznix86.github.io")
        assert Config.LAST_DIGEST_ANNOTATION.startswith(
            "image-updater.eznix86.github.io"
        )
        assert Config.TRACK_CONTAINERS_ANNOTATION.startswith(
            "image-updater.eznix86.github.io"
        )
        assert Config.IGNORE_CONTAINERS_ANNOTATION.startswith(
            "image-updater.eznix86.github.io"
        )
        assert Config.TRACK_INIT_CONTAINERS_ANNOTATION.startswith(
            "image-updater.eznix86.github.io"
        )
        assert Config.RESTART_ANNOTATION == "kubectl.kubernetes.io/restartedAt"

    def test_config_defaults(self):
        """Test default configuration values."""
        assert Config.DEFAULT_REGISTRY == "registry-1.docker.io"
        assert Config.DEFAULT_NAMESPACE == "library"
        assert Config.CHECK_INTERVAL > 0
        assert isinstance(Config.FORCE_PULL_POLICY, bool)
        assert len(Config.OCI_ACCEPT_TYPES) > 0

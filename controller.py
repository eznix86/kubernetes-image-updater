"""Kubernetes Image Updater Controller.

A Kopf-based operator that watches Kubernetes workloads and automatically
restarts them when container image digests change.
"""

import datetime
import os
from dataclasses import dataclass
from typing import Protocol, Optional
from enum import Enum

import kopf
import kubernetes
import requests
from kubernetes.config import ConfigException

class Config:
    """Application configuration."""

    # Annotations
    ENABLE_ANNOTATION = "image-updater.eznix86.github.io/enabled"
    LAST_DIGEST_ANNOTATION = "image-updater.eznix86.github.io/last-digest"
    TRACK_CONTAINERS_ANNOTATION = "image-updater.eznix86.github.io/track-containers"
    IGNORE_CONTAINERS_ANNOTATION = "image-updater.eznix86.github.io/ignore-containers"
    TRACK_INIT_CONTAINERS_ANNOTATION = (
        "image-updater.eznix86.github.io/track-init-containers"
    )
    RESTART_ANNOTATION = "kubectl.kubernetes.io/restartedAt"

    # Defaults
    DEFAULT_INTERVAL = 300
    DEFAULT_REGISTRY = "registry-1.docker.io"
    DEFAULT_NAMESPACE = "library"

    # Environment
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", str(DEFAULT_INTERVAL)))
    FORCE_PULL_POLICY = (
        os.getenv("AUTOMATICALLY_SET_IMAGE_PULL_POLICY_TO_ALWAYS", "false").lower()
        == "true"
    )

    OCI_ACCEPT_TYPES = [
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    ]


@dataclass(frozen=True)
class ImageReference:
    """Parsed container image reference."""

    registry: str
    repository: str
    tag: str

    @classmethod
    def parse(cls, image: str) -> "ImageReference":
        """Parse image string into components.

        Examples:
            nginx:latest -> registry-1.docker.io/library/nginx:latest
            myregistry.io/app:v1 -> myregistry.io/app:v1
        """
        name, tag = image.rsplit(":", 1)

        # Handle Docker Hub shorthand
        if "/" not in name:
            return cls(
                registry=Config.DEFAULT_REGISTRY,
                repository=f"{Config.DEFAULT_NAMESPACE}/{name}",
                tag=tag,
            )

        # Check if first part is a registry (contains . or :)
        first_part = name.split("/")[0]
        if "." in first_part or ":" in first_part:
            registry, repository = name.split("/", 1)
        else:
            registry = Config.DEFAULT_REGISTRY
            repository = name

        return cls(registry=registry, repository=repository, tag=tag)


@dataclass
class ContainerInfo:
    """Information about a tracked container."""

    name: str
    image: str
    image_pull_policy: Optional[str] = None

    @property
    def needs_pull_policy_update(self) -> bool:
        """Check if imagePullPolicy needs to be set to Always."""
        return self.image_pull_policy != "Always"


@dataclass
class DigestMap:
    """Container name to digest mapping."""

    digests: dict[str, str]

    @classmethod
    def from_annotation(cls, annotation_value: Optional[str]) -> "DigestMap":
        """Parse annotation value into digest map.

        Supports both legacy single-digest format and new multi-container format.
        Format: "container1:sha256:abc,container2:sha256:def"
        """
        if not annotation_value:
            return cls({})

        # Detect legacy format (single digest without container name)
        if (
            annotation_value.startswith(("sha256:", "sha384:", "sha512:"))
            and "," not in annotation_value
        ):
            return cls({"__legacy__": annotation_value})

        # Parse new format
        digests = {}
        for entry in annotation_value.split(","):
            entry = entry.strip()
            if ":" not in entry:
                continue

            name, digest = entry.split(":", 1)
            name, digest = name.strip(), digest.strip()

            if name and digest:
                digests[name] = digest

        return cls(digests)

    def to_annotation(self) -> str:
        """Convert digest map to annotation string."""
        return ",".join(
            f"{name}:{digest}" for name, digest in sorted(self.digests.items())
        )

    def has_changed(self, current: "DigestMap") -> bool:
        """Check if any digests have changed or containers added/removed."""
        # Check for new or changed containers
        for name, digest in current.digests.items():
            if self.digests.get(name) != digest:
                return True

        # Check for removed containers
        for name in self.digests:
            if name not in current.digests and name != "__legacy__":
                return True

        return False

    def migrate_legacy(self, primary_container: str) -> "DigestMap":
        """Migrate legacy single-digest format to new format."""
        if "__legacy__" in self.digests:
            return DigestMap({primary_container: self.digests["__legacy__"]})
        return self


class WorkloadKind(str, Enum):
    """Supported Kubernetes workload types."""

    DEPLOYMENT = "deployment"
    STATEFULSET = "statefulset"
    DAEMONSET = "daemonset"

class ImageUpdaterError(Exception):
    """Base exception for image updater errors."""

    pass


class DigestFetchError(ImageUpdaterError):
    """Failed to fetch image digest."""

    pass


class AuthenticationError(ImageUpdaterError):
    """Registry authentication failed."""

    pass


class Logger(Protocol):
    """Logger protocol for type hints."""

    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class ImageRegistry:
    """Handles interaction with container registries."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()

    def get_digest(self, image_ref: ImageReference) -> str:
        """Fetch content digest for an image."""
        try:
            response = self._fetch_manifest(image_ref)
            digest = response.headers.get("Docker-Content-Digest")

            if not digest:
                raise DigestFetchError(
                    f"No digest header returned for {image_ref.repository}:{image_ref.tag}"
                )

            return digest

        except requests.RequestException as e:
            raise DigestFetchError(f"Failed to fetch manifest: {e}") from e

    def _fetch_manifest(self, image_ref: ImageReference) -> requests.Response:
        """Fetch manifest with authentication handling."""
        headers = {"Accept": ", ".join(Config.OCI_ACCEPT_TYPES)}
        url = f"https://{image_ref.registry}/v2/{image_ref.repository}/manifests/{image_ref.tag}"

        response = self.session.get(url, headers=headers, timeout=self.timeout)

        if response.status_code == 401:
            token = self._get_bearer_token(
                response.headers.get("WWW-Authenticate"), image_ref.repository
            )
            if token:
                headers["Authorization"] = f"Bearer {token}"
                response = self.session.get(url, headers=headers, timeout=self.timeout)

        response.raise_for_status()
        return response

    def _get_bearer_token(
        self, auth_header: Optional[str], repository: str
    ) -> Optional[str]:
        """Request bearer token from registry."""
        if not auth_header:
            return None

        params = self._parse_auth_header(auth_header)
        realm = params.get("realm")

        if not realm:
            return None

        query = {"scope": params.get("scope", f"repository:{repository}:pull")}

        if service := params.get("service"):
            query["service"] = service

        try:
            response = requests.get(realm, params=query, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("token") or data.get("access_token")
        except requests.RequestException:
            return None

    @staticmethod
    def _parse_auth_header(header: Optional[str]) -> dict[str, str]:
        """Parse WWW-Authenticate header."""
        if not header:
            return {}
        scheme, _, params_str = header.partition(" ")

        if scheme.lower() != "bearer":
            return {}

        params = {}
        for part in params_str.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip().strip('"')

        return params


class ContainerSelector:
    """Selects which containers to track based on annotations."""

    @staticmethod
    def select(
        containers: list[ContainerInfo], annotations: Optional[dict[str, str]]
    ) -> list[ContainerInfo]:
        """Determine which containers to track."""
        if annotations is None:
            annotations = {}

        track = annotations.get(Config.TRACK_CONTAINERS_ANNOTATION)
        ignore = annotations.get(Config.IGNORE_CONTAINERS_ANNOTATION)

        if track:
            # Explicit whitelist
            track_names = {name.strip() for name in track.split(",") if name.strip()}
            return [c for c in containers if c.name in track_names]

        if ignore:
            # Blacklist
            ignore_names = {name.strip() for name in ignore.split(",") if name.strip()}
            return [c for c in containers if c.name not in ignore_names]

        # Track all
        return containers


class WorkloadManager:
    """Manages Kubernetes workload resources."""

    def __init__(self, apps_client: kubernetes.client.AppsV1Api):
        self.apps = apps_client

    def restart(
        self,
        kind: WorkloadKind,
        name: str,
        namespace: str,
        digest_map: DigestMap,
        containers: list[ContainerInfo],
        force_pull_policy: bool = False,
    ) -> None:
        """Restart workload with updated annotations."""
        timestamp = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        patch = {
            "metadata": {
                "annotations": {
                    Config.LAST_DIGEST_ANNOTATION: digest_map.to_annotation(),
                }
            },
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            Config.RESTART_ANNOTATION: timestamp,
                        }
                    }
                }
            },
        }

        # Set imagePullPolicy if needed
        if force_pull_policy:
            containers_needing_update = [
                c for c in containers if c.needs_pull_policy_update
            ]
            if containers_needing_update:
                patch["spec"]["template"]["spec"] = {
                    "containers": [
                        {"name": c.name, "imagePullPolicy": "Always"}
                        for c in containers_needing_update
                    ]
                }

        # Apply patch based on workload type
        if kind == WorkloadKind.DEPLOYMENT:
            self.apps.patch_namespaced_deployment(name, namespace, patch)
        elif kind == WorkloadKind.STATEFULSET:
            self.apps.patch_namespaced_stateful_set(name, namespace, patch)
        elif kind == WorkloadKind.DAEMONSET:
            self.apps.patch_namespaced_daemon_set(name, namespace, patch)


class ImageUpdateReconciler:
    """Reconciles workload state with current image digests."""

    def __init__(
        self,
        registry: ImageRegistry,
        workload_manager: WorkloadManager,
        container_selector: ContainerSelector,
        logger: Logger,
    ):
        self.registry = registry
        self.workload_manager = workload_manager
        self.container_selector = container_selector
        self.logger = logger

    def reconcile(
        self, kind: WorkloadKind, name: str, namespace: str, spec: dict, metadata: dict
    ) -> None:
        """Check for image updates and restart workload if needed."""
        # Extract containers from spec
        template = spec.get("template", {})
        pod_spec = template.get("spec", {})

        containers = self._parse_containers(pod_spec.get("containers", []))
        init_containers = self._parse_containers(pod_spec.get("initContainers", []))

        if not containers:
            return

        annotations = metadata.get("annotations", {})

        # Select containers to track
        tracked = self.container_selector.select(containers, annotations)

        # Include init containers if requested
        if annotations.get(Config.TRACK_INIT_CONTAINERS_ANNOTATION) == "true":
            tracked.extend(init_containers)

        if not tracked:
            return

        # Fetch current digests
        current_digests = self._fetch_digests(tracked, kind, name, namespace)
        if current_digests is None:
            return  # Failed to fetch some digests

        # Compare with stored digests
        stored = DigestMap.from_annotation(
            annotations.get(Config.LAST_DIGEST_ANNOTATION)
        )

        # Handle legacy format migration
        if "__legacy__" in stored.digests and tracked:
            self.logger.info(
                f"{kind.value}/{namespace}/{name}: migrating legacy digest format"
            )
            stored = stored.migrate_legacy(tracked[0].name)

        # Check if restart is needed
        if stored.has_changed(current_digests):
            self.logger.info(
                f"{kind.value}/{namespace}/{name}: image(s) changed → restarting"
            )
            self.workload_manager.restart(
                kind=kind,
                name=name,
                namespace=namespace,
                digest_map=current_digests,
                containers=containers,
                force_pull_policy=Config.FORCE_PULL_POLICY,
            )

    def _parse_containers(self, container_list: list[dict]) -> list[ContainerInfo]:
        """Parse container specs into ContainerInfo objects."""
        return [
            ContainerInfo(
                name=c["name"],
                image=c["image"],
                image_pull_policy=c.get("imagePullPolicy"),
            )
            for c in container_list
            if "name" in c and "image" in c
        ]

    def _fetch_digests(
        self,
        containers: list[ContainerInfo],
        kind: WorkloadKind,
        name: str,
        namespace: str,
    ) -> Optional[DigestMap]:
        """Fetch digests for all containers, returning None if any fail."""
        digests = {}
        failed = []

        for container in containers:
            try:
                image_ref = ImageReference.parse(container.image)
                digest = self.registry.get_digest(image_ref)
                digests[container.name] = digest
            except (DigestFetchError, ValueError) as e:
                self.logger.warning(
                    f"Failed to fetch digest for {container.name} ({container.image}): {e}"
                )
                failed.append(container.name)

        if failed:
            self.logger.info(
                f"{kind.value}/{namespace}/{name}: skipping update due to failures: {', '.join(failed)}"
            )
            return None

        return DigestMap(digests)



def create_kubernetes_client() -> kubernetes.client.AppsV1Api:
    """Create Kubernetes API client."""
    try:
        kubernetes.config.load_incluster_config()
    except ConfigException:
        kubernetes.config.load_kube_config()
    return kubernetes.client.AppsV1Api()


# Global dependencies (initialized once)
_apps_client = create_kubernetes_client()
_registry = ImageRegistry()
_workload_manager = WorkloadManager(_apps_client)
_container_selector = ContainerSelector()


def create_reconciler(logger: Logger) -> ImageUpdateReconciler:
    """Create a reconciler with injected dependencies."""
    return ImageUpdateReconciler(
        registry=_registry,
        workload_manager=_workload_manager,
        container_selector=_container_selector,
        logger=logger,
    )


@kopf.timer(
    "apps",
    "v1",
    "deployments",
    interval=Config.CHECK_INTERVAL,
    annotations={Config.ENABLE_ANNOTATION: "true"},
)
def deployment_timer(spec, meta, name, namespace, logger, **_):
    """Timer handler for Deployments."""
    reconciler = create_reconciler(logger)
    reconciler.reconcile(WorkloadKind.DEPLOYMENT, name, namespace, spec, meta)


@kopf.timer(
    "apps",
    "v1",
    "statefulsets",
    interval=Config.CHECK_INTERVAL,
    annotations={Config.ENABLE_ANNOTATION: "true"},
)
def statefulset_timer(spec, meta, name, namespace, logger, **_):
    """Timer handler for StatefulSets."""
    reconciler = create_reconciler(logger)
    reconciler.reconcile(WorkloadKind.STATEFULSET, name, namespace, spec, meta)


@kopf.timer(
    "apps",
    "v1",
    "daemonsets",
    interval=Config.CHECK_INTERVAL,
    annotations={Config.ENABLE_ANNOTATION: "true"},
)
def daemonset_timer(spec, meta, name, namespace, logger, **_):
    """Timer handler for DaemonSets."""
    reconciler = create_reconciler(logger)
    reconciler.reconcile(WorkloadKind.DAEMONSET, name, namespace, spec, meta)


@kopf.on.startup()
def startup(logger, **_):
    """Log startup message."""
    logger.info("kubernetes-image-updater started")

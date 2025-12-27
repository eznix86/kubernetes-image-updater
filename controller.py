import datetime
import os
from typing import Dict, Optional, Tuple

import kopf
import kubernetes
import requests
from kubernetes.config import ConfigException

ENABLE_ANNOTATION = "image-updater.eznix86.github.io/enabled"
LAST_DIGEST_ANNOTATION = "image-updater.eznix86.github.io/last-digest"
RESTART_ANNOTATION = "kubectl.kubernetes.io/restartedAt"

_DEFAULT_INTERVAL = 300
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", str(_DEFAULT_INTERVAL)))
OCI_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"


def _build_apps_client() -> kubernetes.client.AppsV1Api:
    try:
        kubernetes.config.load_incluster_config()
    except ConfigException:
        kubernetes.config.load_kube_config()
    return kubernetes.client.AppsV1Api()


apps = _build_apps_client()


def parse_image(image: str) -> Tuple[str, str, str]:
    name, tag = image.rsplit(":", 1)

    if "/" not in name:
        return "registry-1.docker.io", f"library/{name}", tag

    first = name.split("/")[0]
    if "." in first or ":" in first:
        registry, repo = name.split("/", 1)
    else:
        registry = "registry-1.docker.io"
        repo = name

    return registry, repo, tag


def _parse_www_authenticate(header: Optional[str]) -> Dict[str, str]:
    if not header:
        return {}
    scheme, _, params = header.partition(" ")
    if scheme.lower() != "bearer":
        return {}
    parsed: Dict[str, str] = {}
    for part in params.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key.strip()] = value.strip().strip('"')
    return parsed


def _request_bearer_token(header: Optional[str], repo: str) -> Optional[str]:
    params = _parse_www_authenticate(header)
    realm = params.get("realm")
    if not realm:
        return None

    query = {}
    if service := params.get("service"):
        query["service"] = service
    scope = params.get("scope") or f"repository:{repo}:pull"
    query["scope"] = scope

    response = requests.get(realm, params=query, timeout=10)
    response.raise_for_status()
    payload = response.json()
    return payload.get("token") or payload.get("access_token")


def _fetch_manifest(registry: str, repo: str, tag: str) -> requests.Response:
    session = requests.Session()
    headers = {"Accept": OCI_ACCEPT}
    url = f"https://{registry}/v2/{repo}/manifests/{tag}"

    response = session.get(url, headers=headers, timeout=10)
    if response.status_code == 401:
        token = _request_bearer_token(response.headers.get("WWW-Authenticate"), repo)
        if token:
            headers = {**headers, "Authorization": f"Bearer {token}"}
            response = session.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response


def get_digest(image: str) -> str:
    registry, repo, tag = parse_image(image)
    response = _fetch_manifest(registry, repo, tag)

    digest = response.headers.get("Docker-Content-Digest")
    if not digest:
        raise ValueError(f"Registry did not return digest header for {image}")

    return digest


def rollout_restart(kind: str, name: str, namespace: str, digest: str) -> None:
    now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    body = {
        "metadata": {
            "annotations": {
                LAST_DIGEST_ANNOTATION: digest,
            }
        },
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        RESTART_ANNOTATION: now,
                    }
                }
            }
        },
    }

    if kind == "deployment":
        apps.patch_namespaced_deployment(name, namespace, body)
    elif kind == "statefulset":
        apps.patch_namespaced_stateful_set(name, namespace, body)
    elif kind == "daemonset":
        apps.patch_namespaced_daemon_set(name, namespace, body)


def reconcile(kind: str, spec, meta, name: str, namespace: str, logger, **_):
    template = (spec or {}).get("template", {})
    pod_spec = template.get("spec", {})
    containers = pod_spec.get("containers", [])
    if not containers:
        return

    image = containers[0].get("image")
    if not image:
        return

    try:
        digest = get_digest(image)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to fetch digest for {image}: {exc}")
        return

    annotations = (meta or {}).get("annotations") or {}
    last = annotations.get(LAST_DIGEST_ANNOTATION)

    if digest != last:
        logger.info(f"{kind}/{namespace}/{name}: image changed → restart")
        rollout_restart(kind, name, namespace, digest)


@kopf.timer(
    "apps",
    "v1",
    "deployments",
    interval=CHECK_INTERVAL,
    annotations={ENABLE_ANNOTATION: "true"},
)
def deployment_timer(**kwargs):
    reconcile("deployment", **kwargs)


@kopf.timer(
    "apps",
    "v1",
    "statefulsets",
    interval=CHECK_INTERVAL,
    annotations={ENABLE_ANNOTATION: "true"},
)
def statefulset_timer(**kwargs):
    reconcile("statefulset", **kwargs)


@kopf.timer(
    "apps",
    "v1",
    "daemonsets",
    interval=CHECK_INTERVAL,
    annotations={ENABLE_ANNOTATION: "true"}
)
def daemonset_timer(**kwargs):
    reconcile("daemonset", **kwargs)


@kopf.on.startup()
def startup(logger, **_):
    logger.info("kubernetes-image-updater started")

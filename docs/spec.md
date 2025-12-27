# Kubernetes Image Updater — Specification

**Project:** Kubernetes Image Updater
**Repository:** [https://github.com/eznix86/kubernetes-image-updater](https://github.com/eznix86/kubernetes-image-updater)
**Status:** Stable (v1)
**Scope:** Kubernetes-native image digest–based restarts
**Non-Goals:** GitOps, version selection, CI/CD orchestration

---

## 1. Overview

Kubernetes Image Updater is a lightweight Kubernetes operator that automatically triggers rolling restarts of Kubernetes workloads when the **OCI image digest behind an existing image tag changes**.

The operator is inspired by Docker Watchtower but is **fully Kubernetes-native**, relying exclusively on standard Kubernetes rollout semantics.

The operator **does not modify image tags**, **does not compare versions**, and **does not manage Git state**.

---

## 2. Core Principles

1. **Digest-based detection**
   Updates are detected solely by comparing OCI image digests.

2. **Kubernetes-native behavior**
   Restarts are triggered using the same mechanism as:

   ```bash
   kubectl rollout restart
   ```

3. **Opt-in via annotations**
   Only explicitly annotated workloads are managed.

4. **Controller-driven restarts**
   Pods are never deleted directly. Kubernetes controllers handle restarts.

5. **Registry-agnostic**
   Any OCI-compliant registry is supported.

---

## 3. Supported Workloads

The operator targets **restartable workloads** that expose a Pod template.

### Supported

* `Deployment`
* `StatefulSet`
* `DaemonSet`
* `ReplicaSet` (implicit via Deployments)

### Not Supported

* `Pod`
* `Job`
* `CronJob`
* Static Pods

---

## 4. Annotation API (v1)

### 4.1 Annotation Namespace

All operator-owned annotations use the following prefix:

```text
image-updater.eznix86.github.io
```

This namespace is authoritative and versioned implicitly.

---

### 4.2 Enable Annotation (Required)

#### Key

```text
image-updater.eznix86.github.io/enabled
```

#### Type

```text
string (boolean semantics)
```

#### Valid Values

* `"true"` — workload is managed
* any other value or absence — workload is ignored

#### Scope

* Applied to the **workload metadata**, not the Pod template

#### Example

```yaml
metadata:
  annotations:
    image-updater.eznix86.github.io/enabled: "true"
```

---

### 4.3 Internal State Annotation (Managed by Operator)

#### Key

```text
image-updater.eznix86.github.io/last-digest
```

#### Purpose

Stores the last observed OCI image digest to ensure idempotency and avoid restart loops.

#### Ownership

* MUST be written and updated only by the operator
* MUST NOT be set manually by users

---

### 4.4 Restart Annotation (Kubernetes Standard)

#### Key

```text
kubectl.kubernetes.io/restartedAt
```

#### Purpose

Triggers a rolling restart by mutating the Pod template.

#### Behavior

* Identical to `kubectl rollout restart`
* MUST be written to:

  ```yaml
  spec.template.metadata.annotations
  ```

#### Ownership

* Shared Kubernetes convention
* MUST NOT be replaced by a custom annotation

---

## 5. Functional Behavior

### 5.1 Reconciliation Loop

For each enabled workload:

1. Identify the target container image
2. Resolve the image reference
3. Fetch the remote OCI manifest
4. Extract the image digest
5. Compare against `last-digest`
6. If changed:

   * Patch the Pod template with `restartedAt`
   * Update `last-digest`

---

### 5.2 Restart Semantics

* The operator **MUST NOT**:

  * Delete Pods
  * Scale workloads
  * Modify image tags
  * Modify controller metadata

* The operator **MUST**:

  * Patch only `spec.template.metadata.annotations`
  * Allow Kubernetes to perform rolling updates according to workload strategy

---

## 6. Image Resolution Rules

### 6.1 OCI Compliance

The operator MUST support any OCI-compliant registry implementing the Docker Registry HTTP API v2.

### 6.2 Image Reference Parsing

Supported formats include:

```text
nginx:latest
org/app:stable
ghcr.io/org/app:1.2.3
registry.example.com/team/app:prod
```

### 6.3 Default Registry Resolution

If no registry is specified:

* Registry: `registry-1.docker.io`
* Repository prefix: `library/` (if required)

This follows Docker-compatible resolution rules.

---

## 7. Registry Authentication (Out of Scope for v1)

Authentication mechanisms are implementation-dependent and MAY include:

* Public registry access
* Node-level credentials
* Kubernetes `imagePullSecrets`

The specification does not mandate a specific authentication mechanism.

---

## 8. Container Selection

### v1 Rule

* The **first container** in `spec.template.spec.containers` is used.

### Future Extension

Additional annotations MAY allow explicit container selection.

---

## 9. Failure Handling

* Registry errors MUST NOT crash the operator
* Failures MUST be logged
* No retries are guaranteed within a single reconciliation cycle
* State MUST remain unchanged on failure

---

## 10. Security Considerations

* The operator requires **read access** to workloads
* The operator requires **patch access** to:

  * Deployments
  * StatefulSets
  * DaemonSets

Minimal RBAC MUST be used.

---

## 11. Non-Goals (Explicit)

The operator intentionally does **NOT**:

* Perform semantic version comparison
* Select the “latest” version
* Scan all registry tags
* Integrate with Git
* Replace GitOps tools
* Act as a CI/CD system

---

## 12. Compatibility

The operator is designed to be compatible with:

* `kubectl rollout restart`
* GitOps tools (Flux, Argo CD)
* Horizontal Pod Autoscaler
* PodDisruptionBudgets
* Standard Kubernetes controllers

---

## 13. Versioning Policy

* Annotation keys under `image-updater.eznix86.github.io` constitute the public API
* Breaking changes MUST be versioned via documentation and releases
* Kubernetes standard annotations MUST remain unchanged

---

## 14. Summary

Kubernetes Image Updater provides:

* Watchtower-style behavior
* Kubernetes-native semantics
* Minimal surface area
* Clear ownership boundaries
* Predictable, safe rollouts

**Digest change → Pod template patch → Kubernetes rolls**

Nothing more. Nothing less.

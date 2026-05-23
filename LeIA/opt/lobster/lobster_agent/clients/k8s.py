import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import yaml
from lightkube import AsyncClient, codecs
from lightkube.config.kubeconfig import KubeConfig
from lightkube.resources.apps_v1 import Deployment, DeploymentScale
from lightkube.resources.autoscaling_v2 import HorizontalPodAutoscaler
from lightkube.resources.core_v1 import (
    ConfigMap,
    Event,
    Namespace,
    Node,
    PersistentVolume,
    PersistentVolumeClaim,
    Pod,
    ResourceQuota,
    Secret,
    Service,
)
from lightkube.resources.networking_v1 import Ingress


class K8sClientError(RuntimeError):
    pass


ALLOWED_MANIFEST_KINDS = {
    "Deployment",
    "Service",
    "ConfigMap",
    "Ingress",
    "PersistentVolumeClaim",
    "Namespace",
    "HorizontalPodAutoscaler",
    "Secret",
    "ResourceQuota",
}
FORBIDDEN_MANIFEST_KINDS = {
    "Secret",
    "ServiceAccount",
    "Role",
    "RoleBinding",
    "ClusterRole",
    "ClusterRoleBinding",
    "Pod",
}
MANIFEST_RESOURCES: dict[str, Any] = {
    "Deployment": Deployment,
    "Service": Service,
    "ConfigMap": ConfigMap,
    "Ingress": Ingress,
    "PersistentVolumeClaim": PersistentVolumeClaim,
    "Namespace": Namespace,
    "HorizontalPodAutoscaler": HorizontalPodAutoscaler,
    "Secret": Secret,
    "ResourceQuota": ResourceQuota,
}


class K8sClient:
    def __init__(self, kubeconfig_path: str, timeout_seconds: float = 10.0) -> None:
        self._kubeconfig_path = kubeconfig_path
        self._timeout_seconds = timeout_seconds
        self._client: AsyncClient | None = None

    async def list_namespaces(self, label_selector: str | None = None) -> list[object]:
        return await self._list(Namespace, labels=_parse_label_selector(label_selector))

    async def get_namespace(self, name: str) -> object:
        return await self._get(Namespace, name)

    async def delete_namespace(self, namespace: str) -> None:
        try:
            await self._get_client().delete(Namespace, namespace)
        except Exception as exc:
            message = f"Failed to delete Kubernetes namespace {namespace}: {exc}"
            raise K8sClientError(message) from exc

    async def list_namespaces_with_label(self, label: str) -> list[object]:
        return await self.list_namespaces(label)

    async def patch_namespace_annotations(
        self,
        namespace: str,
        annotations: dict[str, str],
    ) -> None:
        patch = {"metadata": {"annotations": annotations}}
        try:
            await self._get_client().patch(Namespace, namespace, patch)
        except Exception as exc:
            message = f"Failed to patch Kubernetes namespace {namespace}: {exc}"
            raise K8sClientError(message) from exc

    async def get_namespace_annotations(self, namespace: str) -> dict[str, str]:
        namespace_obj = await self.get_namespace(namespace)
        metadata = _get_attr(namespace_obj, "metadata")
        annotations = _get_attr(metadata, "annotations")
        if not isinstance(annotations, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in annotations.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    async def list_pods(self, namespace: str) -> list[object]:
        return await self._list(Pod, namespace=namespace)

    async def get_pod(self, namespace: str, name: str) -> object:
        return await self._get(Pod, name, namespace=namespace)

    async def delete_pod(self, namespace: str, name: str, force: bool = False) -> None:
        """
        Delete a pod. If the pod has a ReplicaSet/Deployment owner,
        K8s recreates it automatically.
        Pass force=True (grace_period=0) to evict pods stuck Terminating on an
        unreachable node — this removes them from the API immediately without
        waiting for the kubelet to confirm termination.
        """
        try:
            kwargs: dict[str, object] = {"grace_period": 0} if force else {}
            await self._get_client().delete(Pod, name, namespace=namespace, **kwargs)
        except Exception as exc:
            message = f"Failed to delete Kubernetes pod {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def restart_deployment(self, namespace: str, name: str) -> None:
        restarted_at = datetime.now(UTC).isoformat()
        patch = {
            "spec": {
                "template": {
                    "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": restarted_at}}
                }
            }
        }
        try:
            await self._get_client().patch(Deployment, name, patch, namespace=namespace)
        except Exception as exc:
            message = f"Failed to restart Kubernetes deployment {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def scale_deployment(self, namespace: str, name: str, replicas: int) -> None:
        if replicas < 0:
            raise K8sClientError("replicas must be >= 0")
        patch = {"spec": {"replicas": replicas}}
        try:
            await self._get_client().patch(DeploymentScale, name, patch, namespace=namespace)
        except Exception as exc:
            message = f"Failed to scale Kubernetes deployment {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def apply_manifest(self, yaml_text: str) -> dict[str, str]:
        manifest = _parse_single_manifest(yaml_text)
        kind = _manifest_kind(manifest)
        if kind in FORBIDDEN_MANIFEST_KINDS and kind != "Secret":
            raise K8sClientError(f"Manifest kind is forbidden: {kind}")
        if kind not in ALLOWED_MANIFEST_KINDS:
            raise K8sClientError(f"Manifest kind is not allowed: {kind}")
        metadata = _manifest_metadata(manifest)
        name = _required_metadata_value(metadata, "name")
        namespace = _manifest_namespace(manifest)
        resource = MANIFEST_RESOURCES[kind]
        obj = codecs.from_dict(manifest)
        client = self._get_client()
        try:
            await client.get(resource, name, namespace=namespace)
        except Exception:
            try:
                await cast(Any, client.create)(obj, name=name, namespace=namespace)
            except Exception as exc:
                message = f"Failed to create Kubernetes manifest {kind} {namespace}/{name}: {exc}"
                raise K8sClientError(message) from exc
            return {"kind": kind, "namespace": namespace or "", "name": name, "action": "created"}
        try:
            await cast(Any, client.replace)(obj, name=name, namespace=namespace)
        except Exception as exc:
            message = f"Failed to update Kubernetes manifest {kind} {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc
        return {"kind": kind, "namespace": namespace or "", "name": name, "action": "updated"}

    async def update_configmap(self, namespace: str, name: str, data: dict[str, str]) -> None:
        try:
            await self._get_client().patch(
                ConfigMap,
                name,
                {"data": data},
                namespace=namespace,
            )
        except Exception as exc:
            message = f"Failed to update Kubernetes configmap {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def patch_deployment_node_selector(
        self,
        namespace: str,
        name: str,
        node_selector: dict[str, str] | None,
    ) -> None:
        patch = {"spec": {"template": {"spec": {"nodeSelector": node_selector}}}}
        try:
            await self._get_client().patch(Deployment, name, patch, namespace=namespace)
        except Exception as exc:
            message = f"Failed to patch nodeSelector for deployment {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def patch_deployment_placement(
        self,
        namespace: str,
        name: str,
        node_selector: dict[str, str] | None,
        tolerations: list[dict[str, str]] | None,
    ) -> None:
        # tolerations=None leaves the field untouched. To clear them, pass [].
        spec: dict[str, Any] = {"nodeSelector": node_selector}
        if tolerations is not None:
            spec["tolerations"] = tolerations
        patch = {"spec": {"template": {"spec": spec}}}
        try:
            await self._get_client().patch(Deployment, name, patch, namespace=namespace)
        except Exception as exc:
            message = f"Failed to patch placement for deployment {namespace}/{name}: {exc}"
            raise K8sClientError(message) from exc

    async def get_deployment_node_selector(
        self,
        namespace: str,
        name: str,
    ) -> dict[str, str] | None:
        deployment = await self.get_deployment(namespace, name)
        spec = _get_attr(deployment, "spec")
        template = _get_attr(spec, "template")
        pod_spec = _get_attr(template, "spec")
        node_selector = _get_attr(pod_spec, "nodeSelector", "node_selector")
        if not isinstance(node_selector, dict):
            return None
        return {str(k): str(v) for k, v in node_selector.items()}

    async def get_deployment_tolerations(
        self,
        namespace: str,
        name: str,
    ) -> list[dict[str, str]]:
        deployment = await self.get_deployment(namespace, name)
        spec = _get_attr(deployment, "spec")
        template = _get_attr(spec, "template")
        pod_spec = _get_attr(template, "spec")
        tolerations = _get_attr(pod_spec, "tolerations")
        if not isinstance(tolerations, list):
            return []
        result: list[dict[str, str]] = []
        for tol in tolerations:
            if isinstance(tol, Mapping):
                result.append({str(k): str(v) for k, v in tol.items() if v is not None})
            else:
                entry: dict[str, str] = {}
                for field in ("key", "operator", "value", "effect", "tolerationSeconds"):
                    val = getattr(tol, field, None)
                    if val is not None:
                        entry[field] = str(val)
                if entry:
                    result.append(entry)
        return result

    async def get_node_ready(self, name: str) -> bool:
        try:
            node = await self._get(Node, name)
        except Exception as exc:
            message = f"Failed to read node {name}: {exc}"
            raise K8sClientError(message) from exc
        status = _get_attr(node, "status")
        conditions = _get_attr(status, "conditions")
        if not isinstance(conditions, list):
            return False
        for cond in conditions:
            cond_type = _get_attr(cond, "type")
            if str(cond_type) != "Ready":
                continue
            cond_status = _get_attr(cond, "status")
            return str(cond_status) == "True"
        return False

    async def patch_node_unschedulable(self, name: str, unschedulable: bool) -> None:
        patch = {"spec": {"unschedulable": unschedulable or None}}
        try:
            await self._get_client().patch(Node, name, patch)
        except Exception as exc:
            message = f"Failed to patch node {name} unschedulable={unschedulable}: {exc}"
            raise K8sClientError(message) from exc

    async def get_node_taints(self, name: str) -> list[dict[str, str]]:
        try:
            node = await self._get(Node, name)
        except Exception as exc:
            message = f"Failed to read node {name}: {exc}"
            raise K8sClientError(message) from exc
        spec = _get_attr(node, "spec")
        taints = _get_attr(spec, "taints")
        if not isinstance(taints, list):
            return []
        result: list[dict[str, str]] = []
        for taint in taints:
            entry: dict[str, str] = {}
            if isinstance(taint, Mapping):
                for k, v in taint.items():
                    if v is not None:
                        entry[str(k)] = str(v)
            else:
                for field in ("key", "value", "effect"):
                    val = getattr(taint, field, None)
                    if val is not None:
                        entry[field] = str(val)
            if entry:
                result.append(entry)
        return result

    async def list_deployments(self, namespace: str) -> list[object]:
        return await self._list(Deployment, namespace=namespace)

    async def get_deployment(self, namespace: str, name: str) -> object:
        return await self._get(Deployment, name, namespace=namespace)

    async def list_events(self, namespace: str) -> list[object]:
        return await self._list(Event, namespace=namespace)

    async def list_pvcs(self, namespace: str) -> list[object]:
        return await self._list(PersistentVolumeClaim, namespace=namespace)

    async def wait_for_pvc_bound(
        self,
        namespace: str,
        pvc_name: str,
        timeout_seconds: int = 30,
    ) -> bool:
        deadline = datetime.now(UTC).timestamp() + timeout_seconds
        while datetime.now(UTC).timestamp() <= deadline:
            pvc = await self._get(PersistentVolumeClaim, pvc_name, namespace=namespace)
            status = _get_attr(pvc, "status")
            if _get_attr(status, "phase") == "Bound":
                return True
            await asyncio.sleep(1)
        return False

    async def get_pvc_storage_path(
        self,
        namespace: str,
        pvc_name: str,
    ) -> dict[str, str | None]:
        """Resolve the on-disk location of a bound PVC.

        Returns ``{"path": ..., "node": ..., "pv_name": ...}``. Each value can
        be None when the PVC is unbound or the PV does not advertise that
        information. Supports local-path-provisioner, hostPath PVs, and
        smb.csi.k8s.io PVs (path derived from the SMB share root + PV name).
        """

        empty: dict[str, str | None] = {"path": None, "node": None, "pv_name": None}
        pvc = await self._get(PersistentVolumeClaim, pvc_name, namespace=namespace)
        spec = _get_attr(pvc, "spec")
        volume_name = _get_attr(spec, "volumeName", "volume_name")
        if not isinstance(volume_name, str) or not volume_name:
            return empty
        pv = await self._get(PersistentVolume, volume_name)
        pv_spec = _get_attr(pv, "spec")
        local = _get_attr(pv_spec, "local")
        host_path = _get_attr(pv_spec, "hostPath", "host_path")
        raw_path = _get_attr(local, "path") or _get_attr(host_path, "path")
        path = raw_path if isinstance(raw_path, str) else None
        # SMB CSI PVs have no local path — derive it from the Samba share root
        if path is None:
            csi = _get_attr(pv_spec, "csi")
            driver = _get_attr(csi, "driver")
            if isinstance(driver, str) and driver == "smb.csi.k8s.io":
                path = f"/srv/k3s-pvs/{volume_name}"
        return {"path": path, "node": _pv_node(pv_spec), "pv_name": volume_name}

    async def list_ingresses(self, namespace: str) -> list[dict[str, Any]]:
        ingresses = await self._list(Ingress, namespace=namespace)
        return [_ingress_summary(ingress) for ingress in ingresses]

    async def get_resource_quota(self, namespace: str) -> object | None:
        quotas = await self._list(ResourceQuota, namespace=namespace)
        return quotas[0] if quotas else None

    async def close(self) -> None:
        if self._client is None:
            return
        close = cast(Any, self._client.close)
        await close()

    async def _list(
        self,
        resource: Any,
        namespace: str | None = None,
        labels: dict[str, Any] | None = None,
    ) -> list[object]:
        try:
            items = self._get_client().list(resource, namespace=namespace, labels=labels)
            return [item async for item in items]
        except Exception as exc:
            raise K8sClientError(f"Failed to list Kubernetes resource: {exc}") from exc

    async def _get(
        self,
        resource: Any,
        name: str,
        namespace: str | None = None,
    ) -> object:
        try:
            return await self._get_client().get(resource, name, namespace=namespace)
        except Exception as exc:
            raise K8sClientError(f"Failed to get Kubernetes resource {name}: {exc}") from exc

    def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(
                config=KubeConfig.from_file(self._kubeconfig_path),
                timeout=httpx.Timeout(self._timeout_seconds),
            )
        return self._client


def _parse_label_selector(label_selector: str | None) -> dict[str, Any] | None:
    if label_selector is None:
        return None

    labels: dict[str, Any] = {}
    for part in label_selector.split(","):
        key, separator, value = part.partition("=")
        if separator and key and value:
            labels[key] = value
    return labels


def _parse_single_manifest(yaml_text: str) -> dict[str, Any]:
    try:
        documents = list(yaml.safe_load_all(yaml_text))
    except yaml.YAMLError as exc:
        raise K8sClientError(f"Invalid Kubernetes manifest YAML: {exc}") from exc
    documents = [doc for doc in documents if doc is not None]
    if len(documents) != 1:
        raise K8sClientError("Manifest must contain exactly one YAML document")
    manifest = documents[0]
    if not isinstance(manifest, dict):
        raise K8sClientError("Manifest must be a YAML object")
    return cast(dict[str, Any], manifest)


def _manifest_kind(manifest: dict[str, Any]) -> str:
    kind = manifest.get("kind")
    if not isinstance(kind, str) or not kind:
        raise K8sClientError("Manifest kind is required")
    return kind


def _manifest_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise K8sClientError("Manifest metadata is required")
    return cast(dict[str, Any], metadata)


def _required_metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        raise K8sClientError(f"Manifest metadata.{key} is required")
    return value


def _manifest_namespace(manifest: dict[str, Any]) -> str | None:
    if _manifest_kind(manifest) == "Namespace":
        return None
    metadata = _manifest_metadata(manifest)
    namespace = metadata.get("namespace")
    if not isinstance(namespace, str) or not namespace:
        raise K8sClientError("Manifest metadata.namespace is required")
    return namespace


def _get_attr(obj: object | None, *names: str) -> object | None:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return cast(object, obj[name])
        value = getattr(obj, name, None)
        if value is not None:
            return cast(object, value)
    return None


def _pv_node(pv_spec: object | None) -> str | None:
    affinity = _get_attr(pv_spec, "nodeAffinity", "node_affinity")
    required = _get_attr(affinity, "required")
    for term in _sequence_attr(required, "nodeSelectorTerms", "node_selector_terms"):
        for expression in _sequence_attr(term, "matchExpressions", "match_expressions"):
            key = _get_attr(expression, "key")
            if key != "kubernetes.io/hostname":
                continue
            for value in _sequence_attr(expression, "values"):
                if isinstance(value, str) and value:
                    return value
    return None


def _ingress_summary(ingress: object) -> dict[str, Any]:
    metadata = _get_attr(ingress, "metadata")
    spec = _get_attr(ingress, "spec")
    status = _get_attr(ingress, "status")
    return {
        "name": _str_or_empty(_get_attr(metadata, "name")),
        "namespace": _str_or_empty(_get_attr(metadata, "namespace")),
        "hosts": _ingress_hosts(spec),
        "tls": bool(_sequence_attr(spec, "tls")),
        "address": _ingress_address(status),
        "age_minutes": _age_minutes(
            _datetime_attr(metadata, "creationTimestamp", "creation_timestamp")
        ),
    }


def _ingress_hosts(spec: object | None) -> list[str]:
    hosts: list[str] = []
    for rule in _sequence_attr(spec, "rules"):
        host = _get_attr(rule, "host")
        if isinstance(host, str) and host:
            hosts.append(host)
    return hosts


def _ingress_address(status: object | None) -> str | None:
    load_balancer = _get_attr(status, "loadBalancer", "load_balancer")
    for item in _sequence_attr(load_balancer, "ingress"):
        for name in ("hostname", "ip"):
            value = _get_attr(item, name)
            if isinstance(value, str) and value:
                return value
    return None


def _sequence_attr(obj: object | None, *names: str) -> list[object]:
    value = _get_attr(obj, *names)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _datetime_attr(obj: object | None, *names: str) -> datetime | None:
    value = _get_attr(obj, *names)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None


def _age_minutes(created_at: datetime | None) -> int:
    if created_at is None:
        return 0
    return max(0, int((datetime.now(UTC) - created_at).total_seconds() // 60))


def _str_or_empty(value: object | None) -> str:
    return value if isinstance(value, str) else ""

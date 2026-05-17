# Kubeconfig read-only para Lobster

## Propósito

El manifiesto crea un ServiceAccount read-only para Lobster y elimina la necesidad
de usar el kubeconfig admin de K3s. No concede verbos de mutación ni acceso genérico
a Secrets.

## Aplicar el manifiesto

```bash
kubectl apply -f deploy/k8s/lobster-rbac.yaml
```

Validación previa opcional:

```bash
kubectl --dry-run=client apply -f deploy/k8s/lobster-rbac.yaml
```

## Generar el kubeconfig

Ejecutar desde Matrix, donde reside el kubeconfig admin:

```bash
./deploy/k8s/generate-kubeconfig.sh /tmp/lobster-kubeconfig
```

## Desplegar a LeIA

```bash
scp /tmp/lobster-kubeconfig leia:/etc/lobster/kubeconfig
ssh leia "chown root:root /etc/lobster/kubeconfig && chmod 600 /etc/lobster/kubeconfig"
```

## Configurar Lobster

`K8sConfig.kubeconfig_path` debe apuntar a:

```text
/etc/lobster/kubeconfig
```

Esta fase mantiene ese valor por defecto y añade `K8sConfig.in_cluster` para
configuraciones futuras en cluster.

## Verificación

```bash
kubectl --kubeconfig=/etc/lobster/kubeconfig auth can-i delete pods -n default  # no
kubectl --kubeconfig=/etc/lobster/kubeconfig get pods --all-namespaces           # yes
```

## Rollback

```bash
kubectl delete -f deploy/k8s/lobster-rbac.yaml
```

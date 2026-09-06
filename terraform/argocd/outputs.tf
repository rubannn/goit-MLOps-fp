output "argocd_namespace" {
  description = "Namespace Argo CD was deployed into"
  value       = kubernetes_namespace.argocd.metadata[0].name
}

output "argocd_release_name" {
  description = "Name of the Argo CD Helm release"
  value       = helm_release.argocd.name
}

output "argocd_release_status" {
  description = "Status of the Argo CD Helm release"
  value       = helm_release.argocd.status
}

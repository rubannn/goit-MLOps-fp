data "terraform_remote_state" "eks" {
  backend = "s3"
  config = {
    bucket  = "mlops-tfstate-goit-512523811086"
    key     = "fp/eks/terraform.tfstate"
    region  = "us-east-1"
    profile = "goit-terraform"
  }
}

resource "kubernetes_namespace" "argocd" {
  metadata {
    name = var.argocd_namespace
  }
}

resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = var.argocd_chart_version
  namespace  = kubernetes_namespace.argocd.metadata[0].name

  values = [
    file("${path.module}/values/argocd-values.yaml")
  ]
}

resource "kubernetes_manifest" "gitops_applicationset" {
  manifest = {
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "ApplicationSet"
    metadata = {
      name      = "gitops-namespaces"
      namespace = kubernetes_namespace.argocd.metadata[0].name
    }
    spec = {
      generators = [
        {
          git = {
            repoURL  = var.gitops_repo_url
            revision = var.gitops_repo_revision
            directories = [
              { path = "gitops/namespace/*" }
            ]
          }
        }
      ]
      template = {
        metadata = {
          name = "{{path.basename}}"
        }
        spec = {
          project = "default"
          source = {
            repoURL        = var.gitops_repo_url
            targetRevision = var.gitops_repo_revision
            path           = "{{path}}"
          }
          destination = {
            server    = "https://kubernetes.default.svc"
            namespace = "{{path.basename}}"
          }
          syncPolicy = {
            automated = {
              prune    = true
              selfHeal = true
            }
            syncOptions = [
              "CreateNamespace=true"
            ]
          }
        }
      }
    }
  }

  depends_on = [helm_release.argocd]
}

resource "kubernetes_manifest" "gitops_applications" {
  manifest = {
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata = {
      name      = "gitops-applications"
      namespace = kubernetes_namespace.argocd.metadata[0].name
    }
    spec = {
      project = "default"
      source = {
        repoURL        = var.gitops_repo_url
        targetRevision = var.gitops_repo_revision
        path           = "gitops/argocd/applications"
      }
      destination = {
        server    = "https://kubernetes.default.svc"
        namespace = kubernetes_namespace.argocd.metadata[0].name
      }
      syncPolicy = {
        automated = {
          prune    = true
          selfHeal = true
        }
      }
    }
  }

  depends_on = [helm_release.argocd]
}

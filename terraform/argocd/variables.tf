variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "goit-terraform"
}

variable "argocd_namespace" {
  description = "Namespace to deploy Argo CD into"
  type        = string
  default     = "mlops-system"
}

variable "argocd_chart_version" {
  description = "Version of the argo/argo-cd Helm chart"
  type        = string
  default     = "7.7.11"
}

variable "gitops_repo_url" {
  description = "URL of the GitOps repository tracked by the Argo CD ApplicationSet"
  type        = string
  default     = "https://github.com/rubannn/goit-MLOps-fp.git"
}

variable "gitops_repo_revision" {
  description = "Git revision (branch) of the GitOps repository to track"
  type        = string
  default     = "main"
}

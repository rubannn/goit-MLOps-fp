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

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "goit-mlops"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.31"
}

variable "cpu_instance_types" {
  description = "Instance types for the CPU node group. t3.medium is blocked by this AWS account's Free Tier restriction (InvalidParameterCombination); m7i-flex.large (8GB RAM, 2 vCPU) is free-tier-eligible per `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true` and has enough memory for Argo CD + MLflow + MinIO without kubelet MemoryPressure."
  type        = list(string)
  default     = ["m7i-flex.large"]
}

variable "gpu_instance_types" {
  description = "Instance types for the GPU/workload node group. Small instance used to demonstrate workload isolation without incurring GPU costs (also Free Tier-eligible)."
  type        = list(string)
  default     = ["t3.micro"]
}

variable "cpu_desired_size" {
  description = "Desired number of nodes in the cpu-nodes group"
  type        = number
  default     = 2
}

variable "gpu_desired_size" {
  description = "Desired number of nodes in the gpu-nodes group"
  type        = number
  default     = 1
}

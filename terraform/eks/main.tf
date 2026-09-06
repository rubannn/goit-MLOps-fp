module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access = true

  vpc_id     = data.terraform_remote_state.vpc.outputs.vpc_id
  subnet_ids = data.terraform_remote_state.vpc.outputs.private_subnets

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    cpu-nodes = {
      instance_types = var.cpu_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = 1
      max_size     = 3
      desired_size = var.cpu_desired_size

      labels = {
        workload-type = "cpu"
      }
    }

    gpu-nodes = {
      instance_types = var.gpu_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = 1
      max_size     = 3
      desired_size = var.gpu_desired_size

      labels = {
        workload-type = "gpu"
      }

      taints = {
        gpu = {
          key    = "workload-type"
          value  = "gpu"
          effect = "NO_SCHEDULE"
        }
      }
    }
  }

  tags = {
    Project = var.cluster_name
  }
}

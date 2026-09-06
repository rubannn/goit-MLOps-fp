data "terraform_remote_state" "vpc" {
  backend = "s3"
  config = {
    bucket  = "mlops-tfstate-goit-512523811086"
    key     = "fp/vpc/terraform.tfstate"
    region  = "us-east-1"
    profile = "goit-terraform"
  }
}

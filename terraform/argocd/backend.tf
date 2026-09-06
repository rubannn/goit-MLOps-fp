terraform {
  backend "s3" {
    bucket         = "mlops-tfstate-goit-512523811086"
    key            = "fp/argocd/terraform.tfstate"
    region         = "us-east-1"
    profile        = "goit-terraform"
    dynamodb_table = "mlops-tfstate-lock"
    encrypt        = true
  }
}

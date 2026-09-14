locals {
  resource_postfix = "${var.postfix}${var.project_number}"

  tags = {
    Owner       = "mlops-v2"
    Project     = "mlops-v2"
    Environment = "${var.environment}"
    Toolkit     = "terraform"
    Name        = "${var.prefix}"
  }
}
locals {
  resource_postfix              = "${var.postfix}${var.project_number}"
  platform_resource_group_name  = "rg-${var.prefix}-${local.resource_postfix}${var.environment}-platform"
  platform_virtual_network_name = "vnet-${var.prefix}-${local.resource_postfix}${var.environment}-platform"

  tags = {
    Owner       = "mlops-v2"
    Project     = "mlops-v2"
    Environment = "${var.environment}"
    Toolkit     = "terraform"
    Name        = "${var.prefix}"
  }
}
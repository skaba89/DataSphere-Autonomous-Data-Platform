terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

variable "subscription_id" {}
variable "resource_group"  { default = "datasphere-rg" }
variable "location"        { default = "West Europe" }
variable "environment"     { default = "production" }

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group
  location = var.location
  tags     = { environment = var.environment, project = "datasphere" }
}

# ADLS Gen2
resource "azurerm_storage_account" "data_lake" {
  name                     = "datasphere${var.environment}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true
}

resource "azurerm_storage_data_lake_gen2_filesystem" "main" {
  name               = "datasphere"
  storage_account_id = azurerm_storage_account.data_lake.id
}

# Azure Synapse
resource "azurerm_synapse_workspace" "main" {
  name                                 = "datasphere-${var.environment}"
  resource_group_name                  = azurerm_resource_group.main.name
  location                             = azurerm_resource_group.main.location
  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.main.id
  sql_administrator_login              = "datasphere"
  sql_administrator_login_password     = var.synapse_password
  identity { type = "SystemAssigned" }
}

variable "synapse_password" { sensitive = true }

output "adls_account_name" { value = azurerm_storage_account.data_lake.name }
output "synapse_workspace"  { value = azurerm_synapse_workspace.main.name }

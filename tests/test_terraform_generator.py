"""Tests pour le générateur Terraform."""
import pytest
from datasphere.models.request import ArchitectureConstraints
from datasphere.generators.terraform import TerraformGenerator


def _c(cloud="aws", wh="snowflake", deploy="kubernetes", budget="medium",
       lake="s3", **kwargs) -> ArchitectureConstraints:
    return ArchitectureConstraints(
        cloud_provider=cloud, data_warehouse=wh, orchestrator="airflow",
        ingestion="airbyte", transformation="dbt", bi_tool="superset",
        deployment=deploy, security=["RBAC"], budget=budget,
        data_lake=lake, catalog="openmetadata", quality="great-expectations",
        processing_mode="batch", **kwargs,
    )


class TestTerraformGenerator:

    def test_generates_core_files(self):
        p = TerraformGenerator().generate("Test", _c())
        assert "main.tf" in p.files
        assert "variables.tf" in p.files
        assert "outputs.tf" in p.files
        assert "backend.tf" in p.files
        assert ".gitignore" in p.files
        assert "README.md" in p.files
        assert "terraform.tfvars.example" in p.files

    def test_generates_networking_module(self):
        p = TerraformGenerator().generate("Test", _c())
        assert "modules/networking/main.tf" in p.files

    def test_generates_warehouse_module(self):
        p = TerraformGenerator().generate("Test", _c())
        assert "modules/warehouse/main.tf" in p.files

    def test_generates_iam_module(self):
        p = TerraformGenerator().generate("Test", _c())
        assert "modules/iam/main.tf" in p.files

    def test_generates_storage_module_when_lake_set(self):
        p = TerraformGenerator().generate("Test", _c(lake="s3"))
        assert "modules/storage/main.tf" in p.files

    def test_no_storage_module_when_lake_not_set(self):
        p = TerraformGenerator().generate("Test", _c(lake=None))
        assert "modules/storage/main.tf" not in p.files

    def test_generates_kubernetes_module_for_k8s_deploy(self):
        p = TerraformGenerator().generate("Test", _c(deploy="kubernetes"))
        assert "modules/kubernetes/main.tf" in p.files
        assert "modules/monitoring/main.tf" in p.files

    def test_no_kubernetes_module_for_docker_compose(self):
        p = TerraformGenerator().generate("Test", _c(deploy="docker-compose"))
        assert "modules/kubernetes/main.tf" not in p.files

    def test_aws_backend_uses_s3(self):
        p = TerraformGenerator().generate("Test", _c(cloud="aws"))
        assert 'backend "s3"' in p.files["backend.tf"]

    def test_gcp_backend_uses_gcs(self):
        p = TerraformGenerator().generate("Test", _c(cloud="gcp", wh="bigquery"))
        assert 'backend "gcs"' in p.files["backend.tf"]

    def test_azure_backend_uses_azurerm(self):
        p = TerraformGenerator().generate("Test", _c(cloud="azure", wh="azure-synapse"))
        assert 'backend "azurerm"' in p.files["backend.tf"]

    def test_snowflake_warehouse_has_snowflake_resources(self):
        p = TerraformGenerator().generate("Test", _c(wh="snowflake"))
        wh = p.files["modules/warehouse/main.tf"]
        assert "snowflake_database" in wh
        assert "snowflake_warehouse" in wh

    def test_bigquery_warehouse_has_bigquery_resources(self):
        p = TerraformGenerator().generate("Test", _c(cloud="gcp", wh="bigquery"))
        wh = p.files["modules/warehouse/main.tf"]
        assert "google_bigquery_dataset" in wh

    def test_redshift_warehouse_has_redshift_cluster(self):
        p = TerraformGenerator().generate("Test", _c(cloud="aws", wh="redshift"))
        wh = p.files["modules/warehouse/main.tf"]
        assert "aws_redshift_cluster" in wh

    def test_aws_networking_has_vpc(self):
        p = TerraformGenerator().generate("Test", _c(cloud="aws"))
        net = p.files["modules/networking/main.tf"]
        assert "aws_vpc" in net
        assert "aws_subnet" in net
        assert "aws_nat_gateway" in net

    def test_gcp_networking_has_vpc(self):
        p = TerraformGenerator().generate("Test", _c(cloud="gcp", wh="bigquery"))
        net = p.files["modules/networking/main.tf"]
        assert "google_compute_network" in net

    def test_azure_networking_has_vnet(self):
        p = TerraformGenerator().generate("Test", _c(cloud="azure", wh="azure-synapse"))
        net = p.files["modules/networking/main.tf"]
        assert "azurerm_virtual_network" in net

    def test_aws_iam_has_role_and_policy(self):
        p = TerraformGenerator().generate("Test", _c(cloud="aws"))
        iam = p.files["modules/iam/main.tf"]
        assert "aws_iam_role" in iam
        assert "aws_iam_policy" in iam

    def test_gcp_iam_has_service_account(self):
        p = TerraformGenerator().generate("Test", _c(cloud="gcp", wh="bigquery"))
        iam = p.files["modules/iam/main.tf"]
        assert "google_service_account" in iam

    def test_enterprise_budget_uses_larger_instance(self):
        p_low = TerraformGenerator().generate("Test", _c(budget="low"))
        p_ent = TerraformGenerator().generate("Test", _c(budget="enterprise"))
        eks_low = p_low.files.get("modules/kubernetes/main.tf", "")
        eks_ent = p_ent.files.get("modules/kubernetes/main.tf", "")
        assert eks_low != eks_ent  # different instance sizes

    def test_monitoring_has_prometheus_helm(self):
        p = TerraformGenerator().generate("Test", _c(deploy="kubernetes"))
        mon = p.files["modules/monitoring/main.tf"]
        assert "kube-prometheus-stack" in mon or "prometheus" in mon.lower()

    def test_readme_has_terraform_commands(self):
        p = TerraformGenerator().generate("Test", _c())
        readme = p.files["README.md"]
        assert "terraform init" in readme
        assert "terraform plan" in readme
        assert "terraform apply" in readme

    def test_readme_mentions_cloud_and_warehouse(self):
        p = TerraformGenerator().generate("Test", _c(cloud="aws", wh="snowflake"))
        readme = p.files["README.md"]
        assert "aws" in readme.lower()
        assert "snowflake" in readme.lower()

    def test_gitignore_excludes_state_files(self):
        p = TerraformGenerator().generate("Test", _c())
        gi = p.files[".gitignore"]
        assert "*.tfstate" in gi
        assert ".terraform/" in gi
        assert "terraform.tfvars" in gi

    def test_variables_has_project_name(self):
        p = TerraformGenerator().generate("Test", _c())
        assert "project_name" in p.files["variables.tf"]
        assert "environment" in p.files["variables.tf"]

    def test_write_to_disk(self, tmp_path):
        p = TerraformGenerator().generate("Retail pipeline", _c())
        written = p.write(str(tmp_path))
        assert len(written) >= 8
        # files are written under terraform/ subdir or at root, depending on keys
        all_files = list(tmp_path.rglob("main.tf"))
        assert len(all_files) >= 1
        all_net = list(tmp_path.rglob("networking/main.tf"))
        assert len(all_net) >= 1

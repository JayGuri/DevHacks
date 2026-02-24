# terraform/main.tf — OCI Free Tier Infrastructure for Federated Learning
# ============================================================================
# Provisions: VCN + Subnet + IGW + Security List + Object Storage Bucket
#             + 1 Central Server + N Client Nodes (ARM A1.Flex)
# ============================================================================

terraform {
  required_version = ">= 1.3.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

# --- OCI Provider ---

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# ============================================================================
# Data Sources: Latest Ubuntu 22.04 aarch64 (ARM) image
# ============================================================================

data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"

  filter {
    name   = "display_name"
    values = ["\\w*aarch64\\w*"]
    regex  = true
  }
}

locals {
  ubuntu_arm_image_id = data.oci_core_images.ubuntu_arm.images[0].id
}

# ============================================================================
# Networking: VCN, Subnet, Internet Gateway, Route Table, Security List
# ============================================================================

resource "oci_core_vcn" "fl_vcn" {
  compartment_id = var.compartment_ocid
  display_name   = "fedbuff-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "fedbuffvcn"
}

resource "oci_core_internet_gateway" "fl_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fl_vcn.id
  display_name   = "fedbuff-igw"
  enabled        = true
}

resource "oci_core_route_table" "fl_route_table" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fl_vcn.id
  display_name   = "fedbuff-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.fl_igw.id
  }
}

resource "oci_core_security_list" "fl_security_list" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.fl_vcn.id
  display_name   = "fedbuff-security-list"

  # --- Egress: Allow all outbound ---
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  # --- Ingress: SSH (22) ---
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # --- Ingress: FL WebSocket Server (8765) ---
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = var.fl_server_port
      max = var.fl_server_port
    }
  }

  # --- Ingress: HTTP (80) for Dashboard ---
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 80
      max = 80
    }
  }

  # --- Ingress: HTTPS (443) ---
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 443
      max = 443
    }
  }

  # --- Ingress: React Dev Server (3000) ---
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = var.dashboard_port
      max = var.dashboard_port
    }
  }

  # --- Ingress: ICMP (ping for diagnostics) ---
  ingress_security_rules {
    protocol  = "1" # ICMP
    source    = "0.0.0.0/0"
    stateless = false
  }
}

resource "oci_core_subnet" "fl_subnet" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.fl_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "fedbuff-subnet"
  dns_label         = "fedbuffsub"
  route_table_id    = oci_core_route_table.fl_route_table.id
  security_list_ids = [oci_core_security_list.fl_security_list.id]

  # Public subnet — instances get public IPs
  prohibit_public_ip_on_vnic = false
}

# ============================================================================
# Object Storage Bucket for Partition Data
# ============================================================================

resource "oci_objectstorage_bucket" "fl_data_bucket" {
  compartment_id = var.compartment_ocid
  namespace      = var.bucket_namespace
  name           = "fedbuff-non-iid-data"
  access_type    = "NoPublicAccess"

  freeform_tags = {
    "project" = "fedbuff-fl"
    "purpose" = "non-iid-partition-storage"
  }
}

# ============================================================================
# Compute: Central Server (1 OCPU, 6GB RAM)
# ============================================================================

resource "oci_core_instance" "server" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "fedbuff-server"
  shape               = var.instance_shape

  shape_config {
    ocpus         = var.server_ocpus
    memory_in_gbs = var.server_memory_gb
  }

  source_details {
    source_type = "image"
    source_id   = local.ubuntu_arm_image_id
    boot_volume_size_in_gbs = 50
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.fl_subnet.id
    assign_public_ip = true
    display_name     = "fedbuff-server-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(
      templatefile("${path.module}/cloud_init_server.sh", {
        git_repo_url    = var.git_repo_url
        git_branch      = var.git_branch
        server_port     = var.fl_server_port
        dashboard_port  = var.dashboard_port
      })
    )
  }

  freeform_tags = {
    "project" = "fedbuff-fl"
    "role"    = "server"
  }
}

# ============================================================================
# Compute: Client Nodes (count = num_client_nodes)
# Each gets: 1 OCPU, 6GB RAM, unique node_id, server IP injected
# ============================================================================

resource "oci_core_instance" "client_nodes" {
  count = var.num_client_nodes

  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "fedbuff-client-${count.index}"
  shape               = var.instance_shape

  shape_config {
    ocpus         = var.client_ocpus
    memory_in_gbs = var.client_memory_gb
  }

  source_details {
    source_type = "image"
    source_id   = local.ubuntu_arm_image_id
    boot_volume_size_in_gbs = 50
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.fl_subnet.id
    assign_public_ip = true
    display_name     = "fedbuff-client-${count.index}-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(
      templatefile("${path.module}/cloud_init_client.sh", {
        node_id      = count.index
        server_ip    = oci_core_instance.server.public_ip
        server_port  = var.fl_server_port
        bucket_url   = var.bucket_par_url
        git_repo_url = var.git_repo_url
        git_branch   = var.git_branch
      })
    )
  }

  freeform_tags = {
    "project" = "fedbuff-fl"
    "role"    = "client"
    "node_id" = tostring(count.index)
  }
}

# ============================================================================
# Data Source: Availability Domains
# ============================================================================

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# ============================================================================
# Outputs
# ============================================================================

output "server_public_ip" {
  description = "Public IP of the FL central server"
  value       = oci_core_instance.server.public_ip
}

output "server_private_ip" {
  description = "Private IP of the FL central server"
  value       = oci_core_instance.server.private_ip
}

output "client_public_ips" {
  description = "Public IPs of all FL client nodes"
  value       = [for c in oci_core_instance.client_nodes : c.public_ip]
}

output "client_node_ids" {
  description = "Mapping of client instance names to their node_ids"
  value = {
    for idx, c in oci_core_instance.client_nodes :
    c.display_name => idx
  }
}

output "bucket_name" {
  description = "Name of the Object Storage bucket"
  value       = oci_objectstorage_bucket.fl_data_bucket.name
}

output "ssh_to_server" {
  description = "SSH command to connect to the server"
  value       = "ssh ubuntu@${oci_core_instance.server.public_ip}"
}

output "ssh_to_clients" {
  description = "SSH commands to connect to each client node"
  value = [
    for c in oci_core_instance.client_nodes :
    "ssh ubuntu@${c.public_ip}"
  ]
}

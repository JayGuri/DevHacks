# terraform/variables.tf — OCI Provider Variables for Free Tier ARM Deployment
# ============================================================================
# Copy this to terraform.tfvars and fill in your OCI credentials.
# ============================================================================

# --- OCI Authentication ---

variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI user"
  type        = string
}

variable "fingerprint" {
  description = "API key fingerprint"
  type        = string
}

variable "private_key_path" {
  description = "Path to the OCI API private key (.pem file)"
  type        = string
}

variable "region" {
  description = "OCI region (e.g., us-ashburn-1, ap-mumbai-1)"
  type        = string
  default     = "ap-mumbai-1"
}

variable "compartment_ocid" {
  description = "OCID of the compartment to deploy resources into"
  type        = string
}

# --- SSH Access ---

variable "ssh_public_key" {
  description = "Public SSH key for instance access (contents, not path)"
  type        = string
}

# --- Compute Shape (Free Tier ARM) ---

variable "instance_shape" {
  description = "OCI Compute shape. VM.Standard.A1.Flex is Always Free ARM."
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "server_ocpus" {
  description = "Number of OCPUs for the server instance"
  type        = number
  default     = 1
}

variable "server_memory_gb" {
  description = "Memory in GB for the server instance"
  type        = number
  default     = 6
}

variable "client_ocpus" {
  description = "Number of OCPUs per client instance"
  type        = number
  default     = 1
}

variable "client_memory_gb" {
  description = "Memory in GB per client instance"
  type        = number
  default     = 6
}

# --- Client Nodes ---

variable "num_client_nodes" {
  description = "Number of FL client VMs to provision (3 for free tier)"
  type        = number
  default     = 3
}

# --- Object Storage ---

variable "bucket_namespace" {
  description = "OCI Object Storage namespace (find via: oci os ns get)"
  type        = string
}

variable "bucket_par_url" {
  description = "Pre-Authenticated Request URL for the data bucket (created after uploading partitions)"
  type        = string
  default     = ""
}

# --- Application ---

variable "git_repo_url" {
  description = "Git repository URL to clone onto instances"
  type        = string
  default     = "https://github.com/JayGuri/DevHacks.git"
}

variable "git_branch" {
  description = "Git branch to checkout"
  type        = string
  default     = "main"
}

variable "fl_server_port" {
  description = "Port for the FL WebSocket/FastAPI server"
  type        = number
  default     = 8765
}

variable "dashboard_port" {
  description = "Port for the React dashboard"
  type        = number
  default     = 3000
}

# ⚠️ This directory is intentionally empty

The FL server and client code lives in the repository root:

- **Server**: `async_federated_learning/main.py`
- **Client**: `async_federated_learning/client/fl_client.py`

Terraform cloud-init scripts (`terraform/cloud_init_server.sh` and
`terraform/cloud_init_client.sh`) clone the full repo and reference the
root `async_federated_learning/` directory directly.

Previously, this directory contained stale copies of `fl_server.py`,
`fl_client.py`, `cloud_loader.py`, and `mongo_loader.py`. They were
removed because they were out of sync with the actively maintained code.

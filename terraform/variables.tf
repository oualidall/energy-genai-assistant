variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "GCP region (Cloud Run + BigQuery location)."
  default     = "europe-west1"
}

variable "bigquery_dataset" {
  type        = string
  description = "BigQuery dataset holding the RTE tables."
  default     = "rte_energy"
}

variable "container_image" {
  type        = string
  description = "Fully-qualified container image for the Cloud Run service."
}

output "cloud_run_url" {
  description = "Public URL of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.api.uri
}

output "bigquery_dataset" {
  description = "BigQuery dataset ID."
  value       = google_bigquery_dataset.rte_energy.dataset_id
}

output "artifact_registry" {
  description = "Artifact Registry repository path."
  value       = google_artifact_registry_repository.app.name
}

# Release and rollback

Run lint, unit tests and the fixed evaluation set before building one immutable image.
Deploy its digest through a reviewed OpenTofu plan. Configuration remains separate and
credentials use workload identity. Catalog changes create immutable object generations;
validate before updating the current pointer. Rollback restores the previous Cloud Run
revision and catalog generation together.

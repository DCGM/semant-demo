## Development environment

- Local realistic database snapshot is available under `local_data/`.
- Local Weaviate runs from `local_data/weaviate_semant_test`.
- Local SQLite state is `local_data/tasks.db`.
- Shared server databases are not used for normal refactor development.
- Until issue #1 makes SQL configuration injectable, the backend uses a local
  `semant_demo_backend/tasks.db` symlink.
- Issue #3 will establish deterministic test-owned integration fixtures.
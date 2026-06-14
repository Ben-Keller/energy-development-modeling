# Chapter 1: Infrastructure Strategy & Local Cloud Development

This chapter defines the foundational network topology, the multi-environment isolation strategy, and the local development requirements. The coding agent must implement the system such that it is architecturally identical across Local, Staging, and Production environments, differing only in the backing service providers.

---

## 1.1 Azure Cloud Network Architecture
The platform is designed around a **Backend-for-Frontend (BFF) proxy pattern** to isolate heavy computational workloads from the public internet [1].

### 1.1.1 VNet and Subnet Isolation
*   **Virtual Network (VNet):** All persistence and compute resources (PostgreSQL and the Worker VM) must reside within a private virtual network [2, 3].
*   **Private Subnets:** 
    *   **Persistence Subnet:** Contains the **Azure Database for PostgreSQL Flexible Server** [4, 5].
    *   **Compute Subnet:** Contains the **Isolated Compute Worker (Azure VM)** [2, 6].
*   **API Gateway (App Service):** The FastAPI application on Azure App Service acts as the single entry point. It is the only component with a public ingress surface, enforcing **TLS 1.3 encryption on port 443** [2, 7].

### 1.1.2 Ingress and Egress Controls
*   **Worker VM Isolation:** The Compute VM must be provisioned with **no public IP address** [2].
*   **Outbound-Only Communication:** The VM communicates exclusively outwards via **secure AMQP over TLS (port 5671)** to Azure Service Bus and **HTTPS (port 443)** to Azure Blob Storage [2].
*   **M2M Authentication:** All internal service communication must utilize **Azure Managed Identities (RBAC)** instead of fixed access keys, mitigating the risk of credential leakage [8].

---

## 1.2 Environment Isolation Strategy (Staging vs. Production)
The platform follows a **"Shared Service, Logical Isolation"** strategy to balance cost-efficiency with functional parity.

| Service Component | Staging Strategy | Production Strategy |
| :--- | :--- | :--- |
| **Web API (FastAPI)** | Dedicated **Staging Slot** [9, 10] | **Production Slot** [9, 10] |
| **Database (Postgres)** | Logical Database: `edim_db_staging` [11] | Logical Database: `edim_db_production` [11] |
| **Messaging (Bus)** | Dedicated Queue: `execution-queue-staging` [12] | Dedicated Queue: `execution-queue-production` [12] |
| **Object Storage (Blob)**| Container Prefix: `stg-` [13] | Container Prefix: `prod-` [13] |
| **Compute (VM)** | Daemon Service: `worker-stg` [10] | Daemon Service: `worker-prod` [11] |
| **Frontend (SWA)** | **Preview Environment** [14] | **Production Environment** [14] |

### 1.2.1 High Availability and Redundancy
*   **Staging:** Configured for cost-efficiency using Single-Zone deployments and Locally Redundant Storage (LRS) [11, 13].
*   **Production:** Must implement **High Availability (HA)** for the database, **Geo-Redundant Storage (GRS)** for Blobs, and zone-redundant backups [13, 15].

---

## 1.3 Local Development Strategy (Local Cloud)
The development environment must mirror the cloud architecture using a **Docker Compose** stack and service emulators.

### 1.3.1 Docker Compose Components
*   **`edim-api`:** The FastAPI application container built from the `backend/` directory.
*   **`edim-worker`:** The compute daemon container running the `edim_model` CLI.
*   **`edim-db`:** A `postgres:alpine` container for local relational metadata.
*   **`azurite`:** Emulates **Azure Blob Storage** for local dataset and artifact management.
*   **`service-bus-emulator`:** Emulates **Azure Service Bus** to validate the **Peek-Lock** pattern and **Dead-Letter Queue (DLQ)** logic locally [16].

### 1.3.2 Local Persistence and Emulation
*   **Azurite Data:** Use local volume mounting (e.g., `__azurite_data__/`) to ensure that local datasets and artifacts persist across container restarts.
*   **Hot-Reloading:** Mount the `backend/` and `model_runtime/` source folders as volumes to enable real-time code changes without rebuilding images.

---

## 1.4 Git Workflow and Environment Promotion
A **Branch-per-Environment** strategy is required to manage the transition from development to live operations.

1.  **`develop` Branch:** Targeted at the **Local Docker** environment. Uses the `X-EDIM-User-Id` test-header shim for authentication [17].
2.  **`staging` Branch:** Targeted at the **Azure Staging Slot**. Triggered by merging `develop`. This environment must pass the full **Backend Handoff Smoke Test** [18, 19].
3.  **`main` Branch:** Targeted at the **Azure Production Slot**. Triggered by merging `staging` after successful User Acceptance Testing (UAT).

---

## 1.5 Best Practices for Infrastructure
*   **Decoupled Configuration:** No secrets or connection strings may be stored in the repository. Use **environment variables** injected via Azure App Configuration or `.env` files [15].
*   **Identity First:** Use **Managed Identities** for all service-to-service connections (e.g., `DefaultAzureCredential` in Python SDKs) to eliminate the need for fixed keys [8].
*   **Statelessness:** Ensure the API and Compute VM remain entirely stateless; all ephemeral workspace data on the VM must be **purged immediately** after a run reaches a terminal state (succeeded or failed) [20].

# Chapter 2: Identity, Authentication & Multi-Tenancy

This chapter details the transition from the transitional `X-EDIM-User-Id` test-header contract to a production-grade identity architecture. The implementation must replace the local authentication shim with a cryptographically verified OpenID Connect (OIDC) flow using **Microsoft Entra ID** while strictly enforcing server-side data isolation.

---

## 2.1 Identity Provider: Microsoft Entra ID
The platform offloads all user management and token issuance to the official **UNDP Microsoft Entra ID** tenant. 

### 2.1.1 Logical Isolation via App Registrations
To maintain clean environment separation, you must use two distinct App Registrations within the UNDP tenant:
*   **Staging Registration (`EDIM-Staging`):** Used for UAT and handoff testing. It issues tokens valid only for the Staging App Service slot.
*   **Production Registration (`EDIM-Production`):** Used for live operations.
*   **Common Requirement:** Both registrations must be configured as **Single-page applications (SPA)** to support the React frontend and must define custom **Scopes** (e.g., `access_as_user`) that the backend will require.

---

## 2.2 Backend Authentication Middleware
The primary implementation point is **`backend/api_service/api/dependencies.py`**. You must replace the existing `get_current_user_context` function with an OIDC-compliant validator.

### 2.2.1 JWT Validation Logic
Every request to the API (excepting the `/api/system/manifest` health check) must include a Bearer token in the `Authorization` header. The middleware must perform the following checks:
1.  **Signature Verification:** Validate the token signature against the public keys published by the official UNDP Entra ID discovery endpoint.
2.  **Issuer & Tenant ID:** Confirm the `iss` claim matches the expected UNDP tenant URI.
3.  **Audience (`aud`):** Confirm the token was intended for the specific backend Client ID (Staging or Production).
4.  **Expiration (`exp`):** Reject any token that has expired.
5.  **Not Before (`nbf`):** Ensure the token is currently valid.

### 2.2.2 Mapping to `UserContext`
Once a token is validated, you must extract its claims and map them to the stable **`UserContext`** object defined in `backend/api_service/services/users.py`. The internal platform logic relies on these exact fields:
*   **`user_id`:** Map from the token’s `sub` (Subject) or `oid` (Object ID) claim. This is the immutable primary key for ownership.
*   **`display_name`:** Map from the `name` claim.
*   **`email`:** Map from the `preferred_username` or `email` claim.
*   **`organization`:** Extracted from the tenant context or custom claims.
*   **`roles`:** Map from the `roles` or `groups` claim within the JWT.
*   **`is_admin`:** A boolean determined by checking if the user possesses the `EDIM.Admin` role or belongs to an authorized admin group.
*   **`auth_mode`:** Set to `oidc`.

---

## 2.3 Multi-Tenancy & Authorization Logic
EDIM enforces strict **User-Level Data Isolation**. Users must never be able to access or discover projects, runs, or datasets belonging to other identities unless they possess administrative privileges.

### 2.3.1 Server-Side Ownership Enforcement
Authorization must be enforced at the **Service and Repository layers**, not the frontend. 
*   **Immutable Ownership:** Every Project, Model Run, and Dataset Version must be tagged with an `owner_user_id` at the moment of creation. This ID is derived directly from the validated `UserContext.user_id`.
*   **Query Filtering:** All `GET`, `PATCH`, and `DELETE` operations must append a strict ownership filter to the SQL query: `WHERE owner_user_id = :current_user_id`.
*   **Admin Override:** If `UserContext.is_admin` is true, the repository should omit the ownership filter, allowing administrators to list and audit all project records across the platform.

### 2.3.2 Cross-User Data Access
*   **Current Policy:** In the current version of the contract, **projects and runs are not shared across users**. There is no "Collaboration" mode.
*   **Global Datasets:** While the system may ship with "Expert" seeded datasets, all user-uploaded datasets are strictly user-scoped. A model run submitted by User A will only ever use the active dataset versions belonging to User A.

---

## 2.4 Service-to-Service Security (Managed Identities)
Authentication between backend components does not use user tokens. Instead, it uses **Azure Managed Identities (RBAC)**.

*   **Implementation:** Use the `DefaultAzureCredential` from the Azure Identity SDK in the Python backend.
*   **App Service:** The FastAPI instance is granted a System-Assigned Managed Identity. You must assign this identity the following roles:
    *   `Storage Blob Data Contributor` (for Artifact and Dataset storage).
    *   `Azure Service Bus Data Sender/Receiver` (for the Execution Queue).
*   **Compute VM:** The worker VM is also granted a System-Assigned Managed Identity with roles to read from the Service Bus and write to Blob Storage.
*   **Benefit:** This removes all hardcoded connection strings and keys from the environment, using Entra ID for machine-to-machine trust.

---

## 2.5 Best Practices for the Coding Agent
*   **No Speculative Auth:** Do not implement cookie-based or session-based auth. Stick to **Bearer JWTs** as defined in the contract.
*   **Standardized Errors:** If authentication fails, return a `401 Unauthorized` with a clean JSON body. Do not expose internal Azure error codes or tenant details.
*   **Dependency Injection:** Ensure the `UserContext` is injected into FastAPI routes as a dependency, allowing for easy mocking during unit tests (e.g., using the `X-EDIM-User-Id` shim in local dev only).

# Chapter 3: Platform Persistence & Relational Schema (PostgreSQL)

This chapter defines the transition from the local, file-based SQLite metadata store to a production-grade relational database. The implementation must replace the `SQLitePlatformRepository` with a PostgreSQL-backed provider that supports multi-tenant isolation, transactional integrity, and automated schema migrations.

---

## 3.1 Database Infrastructure: Azure Database for PostgreSQL
The platform utilizes **Azure Database for PostgreSQL (Flexible Server)** as its primary metadata engine.

*   **Instance Specification:** 
    *   **Staging:** Burstable (B-series) for cost-efficiency.
    *   **Production:** **General Purpose (D-Series)**, such as the `DC2ads v6` instance, to ensure consistent IOPS and performance for complex multi-run reporting and export tasks [1, 2].
*   **High Availability:** Production instances must enable **High Availability (HA)** and zone-redundant backups to ensure point-in-time recovery and session continuity [1, 3, 4].
*   **Logical Isolation:** Both Staging and Production environments reside on the same server but are isolated into distinct logical databases: `edim_db_staging` and `edim_db_production` [5].

---

## 3.2 The `PlatformRepository` Provider Seam
The FastAPI application depends on the `PlatformRepository` protocol defined in `backend/api_service/services/platform_repository.py`.

*   **Implementation:** Create a new class, `PostgresPlatformRepository`, implementing all methods for managing projects, runs, datasets, reports, and exports [6, 7].
*   **Injection:** This provider must be injected into the FastAPI composition root via the `create_app` hook in `backend/api_service/main.py` [8, 9].
*   **Connection Management:** Use **Azure Managed Identities (RBAC)** for authentication. The backend should connect using a token-based identity rather than a static password [10, 11].

---

## 3.3 Relational Data Model & Schema
The database must track the structural relationships of the workspace model [2].

### 3.3.1 Core Entities
The schema must include the following tables:
*   **Users:** Stores external user references, display names, and roles (e.g., `is_admin`) [12, 13].
*   **Projects:** Tracks project ownership, titles, geography descriptors, and use-case labels [14, 15].
*   **Project Runs:** Stores run configurations, stable `run_id`, active `execution_id`, status (draft, queued, running, terminal), and the derived `execution_queue_message` [16-18].
*   **Dataset Version Metadata:** Stores immutable records for every file upload, including the storage URI, file hash, and validation metrics [12, 19].
*   **Dataset Version Pointers:** Tracks the "active" version of a dataset currently selected by the user [12].
*   **Reports & Exports:** Stores metadata and `storage_ref` objects (provider/container/object-key) for generated artifacts [12, 20, 21].

### 3.3.2 Reference Locking Logic
To protect run provenance, the database must enforce a **Reference Locking** policy:
*   A permanent relationship is established between a model run and the specific **version ID** of the datasets used at submission time [19].
*   **Deletion Constraint:** If a user attempts to delete a dataset version, the relational engine must block the action if it is linked to any existing run record (foreign key constraint) [19].

---

## 3.4 Automated Schema Migrations (Alembic)
Database schema versions are maintained deterministically using the **Alembic** framework [22].

*   **Pipeline Integration:** Schema migrations must run **transactionally** during the deployment sequence.
*   **Execution Boundary:** The command `alembic upgrade head` must be executed by the automation tools **before** the new App Service container is permitted to accept traffic [22].
*   **Contract Validation:** The success of these migrations is a prerequisite for the `GET /api/system/manifest` endpoint to report an `ok = true` state [23, 24].

---

## 3.5 Multi-Tenant Data Security
Data security is enforced directly at the SQL level to ensure strict **User-Level Data Isolation** [25].

*   **Ownership Tagging:** Every project, dataset, and run is tagged with an immutable `owner_user_id` derived from the validated Entra ID token [25].
*   **Mandatory Filtering:** 
    *   **Normal Users:** Every repository query must automatically append a `WHERE owner_user_id = :current_user_id` filter [25, 26].
    *   **Administrators:** If `UserContext.is_admin` is true, the repository permits listing all records to enable global auditing and visibility [26, 27].

---

## 3.6 Implementation Best Practices
*   **Stateless Operations:** Do not store transient run data in the database that should live in the Message Broker (e.g., specific worker retry counters). The database is the source of truth for **stable state history** [28, 29].
*   **Fast Event Inserts:** The `EventStore` provider (Chapter 8) may require high-frequency inserts for runtime events. Optimize this table with appropriate indexing to allow the frontend to poll progress without degrading platform performance [30].


# Chapter 4: Artifact Storage & Descriptor-Based Retrieval

This chapter defines the transition from local filesystem storage to a durable, cloud-native object storage architecture. The implementation must replace the `LocalArtifactStorageService` with a provider that leverages **Azure Blob Storage** while strictly enforcing the platform's descriptor-based retrieval contract [1-3].

---

## 4.1 Storage Infrastructure: Azure Blob Storage
The platform offloads all unstructured data—including input datasets, execution bundles, run artifacts, and compiled reports—to Azure Blob Storage [4-6].

### 4.1.1 Logical Container Isolation
To support the "Shared Service, Logical Isolation" strategy, the implementation must utilize a single Storage Account with prefixed containers for environment separation [6, 7].
*   **Staging Prefix:** `stg-` (e.g., `stg-run-artifacts`).
*   **Production Prefix:** `prod-` (e.g., `prod-run-artifacts`).

### 4.1.2 Required Containers
The following isolated containers must be provisioned for each environment [6]:
*   **`input-datasets/`**: Retains immutable source files uploaded by users.
*   **`execution-bundles/`**: Retains historical frozen configuration JSON bundles transmitted to workers.
*   **`run-artifacts/`**: Retains output data, spatial layers, and visualizations generated by model runs.
*   **`compiled-reports/`**: Retains Markdown documents and summary datasets generated from multi-run project views.

---

## 4.2 The `ArtifactStorageService` Provider Seam
The backend depends on the `ArtifactStorageService` provider defined in `backend/api_service/services/artifact_storage.py` [1].

*   **Cloud Provider Implementation:** Create an `AzureBlobArtifactStorageService` that implements the required read/download semantics [1, 8].
*   **Authentication:** The service must connect using **Azure Managed Identities (RBAC)** via `DefaultAzureCredential`. Do not use static account keys or connection strings in the code [9].
*   **Storage References:** Metadata for reports and exports must utilize **`storage_ref`** objects. These objects contain provider-specific metadata (e.g., container name and object key) instead of local file paths [8, 10, 11].

---

## 4.3 Descriptor-Based Retrieval & SAS Tokens
A fundamental security requirement is that the frontend **never learns physical storage paths**, folder hierarchies, or internal connection strings [12, 13].

### 4.3.1 The Download Workflow
1.  **Request:** The frontend requests an artifact using an alphanumeric **`artifact_id`** (e.g., `GET /api/runs/{run_id}/artifacts/summary_json`) [13-15].
2.  **Authorization:** The API layer first verifies user ownership or administrative access rights for the associated run record [8, 13, 16].
3.  **Resolution:** The backend looks up the internal Blob URI corresponding to that descriptor in the PostgreSQL database [13].
4.  **SAS Generation:** The service generates a secure **Shared Access Signature (SAS) token** URL with a brief validity window (e.g., 15 minutes) [8, 13].
5.  **Redirect:** The API returns a **307 Temporary Redirect** to this secure, direct download stream from Azure Storage [13].

---

## 4.4 Worker Handoff: `worker_staged_upload`
The model runtime (black box) does not write directly to cloud storage. Instead, it follows the **`worker_staged_upload`** protocol [17-19].

1.  **Local Execution:** The worker VM executes the model, writing all declared artifacts into its ephemeral local directory [17, 19].
2.  **Staged Publication:** Upon successful process termination (exit code 0), the worker invokes the `publish_run_artifacts(...)` method [17, 19].
3.  **Upload:** This method loops through all artifacts declared in the `artifact_catalog` and uploads them to the secure `run-artifacts/` container in Blob Storage [19, 20].
4.  **Terminal Update:** Only after the upload is complete does the worker update the run status in PostgreSQL to `succeeded` [19].

---

## 4.5 Artifact Policy & Manifest
The platform's artifact behavior is governed by the **`artifacts.manifest`** section within `inputs/runtime_config.json` [20, 21]. The implementation must honor the following properties for each artifact:
*   **`expose_download`**: Determines if a SAS token can be generated for the frontend [15, 21].
*   **`retain_on_success/failure`**: Governs whether the artifact is uploaded to the cloud during the handoff phase [15, 21].
*   **`required_for_report`**: Identifies data sources for the background report generation service [15, 21].

---

## 4.6 Best Practices for the Coding Agent
*   **Stateless Worker:** Ensure the compute worker VM executes a clean-up script to purge its local ephemeral directories immediately after a successful upload to Blob Storage [19].
*   **Direct-to-Object Downloads:** Ensure the `download_response_for_artifact` method avoids intermediate proxying through the App Service; use 307 Redirects to SAS URLs to offload high-bandwidth transfers to Azure Storage [8, 13].
*   **Validation:** Use `DefaultAzureCredential` to ensure the same code works in Staging and Production without modification of credentials [9].


# Chapter 5: Dataset Versioning & Reference Locking

This chapter defines the transition from a local filesystem-based dataset manager to a production-grade, user-scoped dataset repository. The implementation must replace the `LocalDatasetRepository` with an Azure-backed provider that ensures data provenance through immutable versioning and strict reference locking.

---

## 5.1 Dataset Infrastructure & Cataloging
The platform manages input datasets as user-level assets that are reusable across multiple projects [1, 2].

*   **Provider Seam:** Implement the `DatasetRepository` protocol defined in `backend/api_service/services/dataset_repository.py` [3, 4].
*   **Cloud Target:** 
    *   **Metadata:** Store dataset descriptors, validation metrics, and version pointers in **Azure Database for PostgreSQL** [5, 6].
    *   **Files:** Store actual data files in **Azure Blob Storage** within the `input-datasets/` container [6, 7].
*   **Injection:** The new `AzureDatasetRepository` must be injected into the FastAPI composition root in `backend/api_service/main.py` [8, 9].

---

## 5.2 User-Scoped Immutability & Versioning
To protect modeling integrity, every file upload is treated as an **immutable version** [9].

### 5.2.1 Data Isolation
*   **User Ownership:** Datasets are stored at the user level. The system must enforce server-side isolation ensuring users only see and use their own datasets [9, 10].
*   **Immutable Storage:** When a user uploads a revised file, it is saved as a new version with a unique hashed filename in Blob Storage; existing versions are never overwritten [6, 9, 11].

### 5.2.2 Version Management
*   **Active Pointers:** The repository must maintain "active version" pointers in PostgreSQL for each dataset [6, 12, 13].
*   **Activation Logic:** The `activate_version(...)` method updates the pointer to a different historical version without modifying the underlying storage object [13].

---

## 5.3 Reference Locking Logic
A critical requirement for model reproducibility is that the datasets used in a submitted run must remain available indefinitely [11, 14].

*   **Submission Snapshot:** When a run is submitted, the backend records the specific **version ID** of every dataset used at that exact moment [6, 15].
*   **Deletion Policy:**
    *   **Soft Deletion/Archiving:** Users may "delete" or archive a dataset version from their active catalog [16, 17].
    *   **Destructive Blocking:** If a user attempts to permanently delete a dataset version that is linked to any existing run record, the repository must **block the request** with a logical or foreign-key constraint violation [6, 11].
    *   **Provenance Rule:** Once a dataset is referenced by a submitted run, it is locked to preserve the run's provenance [11].

---

## 5.4 Dataset Staging Modes
The backend communicates how datasets should be accessed by the worker through `dataset_staging_mode` defined in `inputs/runtime_config.json` [18, 19].

*   **`copy_to_run` (Staging/Production Default):** The worker downloads the resolved input files from Blob Storage into a local `inputs/datasets/` directory within the run package before execution [18, 20, 21].
*   **`object_reference`:** A cloud-specific mode where the run bundle contains durable object-storage URIs, allowing the worker to stream data directly from Blob Storage if supported by the model runtime [18, 20].
*   **`reference`:** A local-only mode where the bundle points to existing filesystem paths [18, 20].

---

## 5.5 Ingestion Security & Validation
The `DatasetRepository` must implement programmatic multi-stage checks before persisting data to the cloud [22].

1.  **Size Restrictions:** Enforce HTTP payload limits to drop oversized requests immediately [22].
2.  **MIME/Type Filtering:** Verify uploads against an explicit whitelist of formats: **CSV, Excel, GeoJSON, and JSON** [22, 23].
3.  **Structural Parsing:** Before confirming storage, the service must parse the data into memory to validate:
    *   **Structural Integrity:** Check for file parseability and consistent headers [22, 23].
    *   **Mapping Accuracy:** Confirm the data aligns with the expected model input properties [23].
4.  **Error Handling:** Return safe, user-facing diagnostic error arrays for malformed files without exposing internal system stack traces [22, 24].

---

## 5.6 Best Practices for Implementation
*   **Stateless Uploads:** Use stream-uploads to Azure Blob Storage to avoid saturating the App Service's local disk during large file transfers [6].
*   **Manifest Integrity:** Ensure the `runtime_dataset_manifest` method returns a complete snapshot of the active user's datasets so that every run remains self-contained [13, 25].
*   **Diagnostic Transparency:** Expose the result of dataset validation in the UI's "Environment Setup" panel, clearly marking if placeholder or invalid data is being used [26, 27].



# Chapter 6: Durable Messaging & Job State Machine

This chapter defines the transition from an in-memory job manager to a durable, asynchronous messaging architecture. The implementation must replace the `JobManager` and `LocalExecutionQueue` with **Azure Service Bus**, establishing a resilient seam between the FastAPI orchestration layer and the isolated compute workers.

---

## 6.1 Messaging Infrastructure: Azure Service Bus
The platform utilizes **Azure Service Bus** as the primary message broker to handle long-running simulations (up to several minutes) without blocking the web API.

### 6.1.1 Tier and Strategy
*   **Tier Requirement:** Use the **Standard Tier**. This is required to support **Message Sessions** (for guaranteed FIFO sequencing), multiple queues within a single namespace (Staging vs. Production), and **transactions** between the database and the broker [150, Conversation History].
*   **Logical Queues:** 
    *   **Staging:** `execution-queue-staging`.
    *   **Production:** `execution-queue-production`.
*   **Reliability Features:** Enable **Dead-Lettering on Message Expiration** and **Peek-Lock** mechanisms [1, 2].

---

## 6.2 The `ExecutionQueue` Provider Seam
The backend depends on the `ExecutionQueue` protocol defined in `backend/api_service/runtime/stores.py`.

*   **Cloud Implementation:** Create `AzureServiceBusQueue`, replacing the local `JobManager` internals [3, 4].
*   **Transactional Enqueueing:** The API must create the run record in PostgreSQL **transactionally** before enqueuing the message to the Service Bus [5].
*   **Payload Contract:** The queue message must strictly follow the **`ExecutionQueueMessage`** schema, containing [5-7]:
    *   `execution_id`: The unique attempt identifier.
    *   `run_id`: The stable result namespace.
    *   `project_id`: The parent project context.
    *   `user_id`: The initiating user's identifier for ownership validation.
    *   `request_payload`: The normalized model configuration.
    *   `attempt_count`: Tracking for the execution retry policy.

---

## 6.3 Run State Machine & Execution Lifecycle
The system enforces a strict state machine to manage model execution [8, 9].

### 6.3.1 Allowed Statuses and Transitions
*   **`draft`**: The initial state. Editable by the user.
*   **`queued`**: Transitioned when the user hits `/submit`. The `ExecutionQueueMessage` is now in the Service Bus.
*   **`running`**: Transitioned when a worker node picks up the message and begins the `preflight` stage.
*   **Terminal States**:
    *   **`succeeded`**: Model execution completed (exit code 0) and artifacts published.
    *   **`failed`**: Model crash, timeout, or non-zero exit code.
    *   **`cancelled`**: Manual user intervention via `/cancel`.

### 6.3.2 Terminal State Consistency
`GET /api/executions/{execution_id}/status` should fall back to the persisted project run record in PostgreSQL when in-memory worker state is unavailable, making the database the primary source of truth for terminal history [10].

---

## 6.4 Peek-Lock Reliability Pattern
To ensure no job is lost due to worker crashes, the implementation must follow the **Peek-Lock** protocol [11, 12]:

1.  **Lock on Pickup:** When a worker retrieves a message, it is "locked" and invisible to other workers but **not deleted** from the queue.
2.  **Heartbeat Renewal:** While the model is running, the worker daemon must renew the message lock every **60 seconds**.
3.  **Automatic Recovery:** If the worker fails or the heartbeat stops, the lock expires, and the message automatically returns to the queue for another healthy worker to pick up.
4.  **Completion:** The message is deleted from the queue **only** after the worker verifies the terminal state (success or failure) has been persisted to the database.

---

## 6.5 Execution Attempts & Retry Policy
The system tracks every worker engagement through **`execution_attempt`** records [5, 13].

*   **Attempt Logging:** Every time a worker accepts a message, it creates a row in the `execution_attempts` table, including its `worker_id` and the start timestamp.
*   **Retry Policy:** Defined in `inputs/runtime_config.json`. If an execution fails, the worker incrementing the `attempt_count` in the message and re-queues it, provided it has not exceeded the maximum attempts limit (e.g., 3 attempts) [6, 13].
*   **Dead-Lettering:** Messages that exceed the retry limit or are consistently non-viable must be moved to the **Dead-Letter Queue (DLQ)** for operational auditing [1].

---

## 6.6 Cancellation Propagation
The system must support the cancellation of active runs [5]:
*   **Marker State:** When a user requests cancellation, the API marks the run status in PostgreSQL as `cancelled` and sets a `cancellation_requested` flag.
*   **Worker Interruption:** The worker daemon must check this flag during its heartbeat/polling loop and terminate the active model subprocess if a cancellation is detected.

---

## 6.7 Best Practices for Implementation
*   **Async Dispatch:** Use asynchronous Python clients (`azure-servicebus`) to ensure the FastAPI loop remains responsive during job submission.
*   **Visibility Timeouts:** Ensure the Service Bus `LockDuration` is long enough to cover the time between worker heartbeats.
*   **Statelessness:** The worker must treat the queue message as the complete set of instructions required to recreate the environment, as workers are entirely stateless [14, 15].


# Chapter 7: Isolated Compute Worker & CLI Contract

This chapter defines the technical requirements for the **Isolated Compute Layer**. The coding agent must implement the compute worker as a stateless background daemon that treats the mathematical model as a "black box" executable, adhering strictly to the CLI contract and the staged-upload handoff protocol.

---

## 7.1 Compute Infrastructure: Isolated Azure VM
Heavy mathematical execution (Calliope, MRIO) is decoupled from the Web API and hosted on a dedicated Linux environment.

*   **Instance Recommendation:** **Standard_F4as_v6** (or F16s_v2 for higher performance) [1, 2]. This compute-optimized tier provides the high core-to-memory ratio required for energy system simulations.
*   **Networking Isolation:** The VM must have **no public IP address** and no public ingress surface [3]. 
*   **Daemon Operation:** The VM runs a continuous, lightweight background daemon that acts as an active consumer for the **Azure Service Bus** queue [2, 4].
*   **Authentication:** The daemon must use a **System-Assigned Managed Identity** to authenticate with Service Bus (to retrieve messages) and Blob Storage (to download bundles and upload results) [5].

---

## 7.2 The "Black-Box" Model CLI Contract
The backend treats the model runtime (`model_runtime/edim_model/`) as an opaque executable [2, 6, 7]. The worker interacts with it exclusively through three CLI commands:

1.  **`python -m edim_model.cli catalog`**: Returns a JSON object containing the `scenario_catalog` and `architecture_catalog` [8, 9].
2.  **`python -m edim_model.cli preflight --bundle <path_to_bundle>`**: Validates the input bundle configuration without initiating a full solve [9].
3.  **`python -m edim_model.cli run --bundle <path_to_bundle>`**: Executes the full simulation sequence [9].

**Note:** The `PYTHONPATH` or container environment must ensure that the `model_runtime/` directory is importable before these commands are invoked [9].

---

## 7.3 Workspace Management & Execution Lifecycle
The worker operates in a stateless, ephemeral manner. Every execution must be entirely self-contained.

### 7.3.1 Ephemeral Workspace
For every message received, the worker must provision an isolated directory on its local drive named after the **`execution_id`** [4]. This directory contains the following layout [10]:
*   `inputs/`: Contains the `request_bundle.json` and staged datasets.
*   `work/`: Temporary files generated during runtime.
*   `artifacts/`: Destination for declared output files.
*   `logs/`: Runtime JSONL events and model-specific logs.

### 7.3.2 Workspace Staging (`copy_to_run`)
In the default **`copy_to_run`** mode, the worker must download all input datasets resolved in the `dataset_manifest` from Blob Storage into the local `inputs/datasets/` folder before invoking the model [4, 11]. This ensures the model runs against a local, immutable snapshot of the data.

### 7.3.3 The Purge Policy
Immediately upon reaching a terminal state (succeeded or failed) and verifying that data handoff is complete, the worker **must execute a clean-up script** to delete the local execution directory [4]. This prevents storage saturation on the VM disk.

---

## 7.4 Artifact Handoff: `worker_staged_upload`
The worker is responsible for moving successful results from its local disk to durable cloud storage before finalizing the run state.

1.  **Solve:** The model process terminates with exit code `0`.
2.  **Identification:** The worker reads the `artifact_catalog` provided in the run bundle to identify which files must be retained [12, 13].
3.  **Upload:** The worker uploads these declared artifacts to the `run-artifacts/` container in **Azure Blob Storage** [4, 14].
4.  **Terminal Update:** Only after the upload is verified as successful does the worker update the run status in PostgreSQL to **`succeeded`** [4].

---

## 7.5 Process Monitoring & Reliability
*   **Event Interception:** The daemon must intercept the standard output (`stdout`) of the model subprocess. Every structured log line must be formatted into a **`runtime_event_v1`** payload and persisted to the `EventStore` (see Chapter 8) [9, 15].
*   **Lock Maintenance:** During execution, the worker must maintain the **Peek-Lock** on the Service Bus message by renewing it every **60 seconds** [4, 16].
*   **Cancellation Check:** The daemon must periodically check the `cancellation_requested` flag in the database. If set, it must immediately terminate the model subprocess and mark the execution as `cancelled` [4, 17].

---

## 7.6 Best Practices for the Coding Agent
*   **Statelessness is Absolute:** Never assume files from a previous run exist on the worker disk.
*   **Subprocess Safety:** Always use secure subprocess invocation (e.g., `subprocess.run` with proper argument escaping) and implement a configurable **execution timeout** to prevent zombie processes [4, 18].
*   **Error Segregation:** Distinguish between **User-Facing Errors** (e.g., model convergence failure) and **Technical Faults** (e.g., VM disk full). Technical faults should trigger a message retry according to the `execution_retry_policy` [4, 19].


# Chapter 8: Runtime Event Store & Live Progress Tracking

This chapter defines the transition from local JSONL log files to a production-grade, cloud-native **Runtime Event Store**. The implementation must enable the frontend to poll and stream real-time execution progress—including milestones, warnings, and final result summaries—without requiring direct connectivity to the isolated compute workers [1, 2].

---

## 8.1 Functional Requirements & Semantics
The `EventStore` provider must support the transition of execution state from the worker's local process to the platform’s durable metadata layer [3].

*   **Provider Seam:** Implement the `EventStore` protocol defined in `backend/api_service/runtime/stores.py` [3, 4].
*   **Required Semantics:**
    *   **`append_event(execution_id, event)`**: Persists a single event object during runtime [5].
    *   **`read_events(execution_id)`**: Returns an ordered list of all events for a specific execution [5].
    *   **`import_event_log(execution_id, source_path)`**: Allows a worker to publish a completed local JSONL log into durable storage upon termination [5].

---

## 8.2 The `runtime_event_v1` Schema
Every event persisted in the store must follow the **`runtime_event_v1`** schema to ensure compatibility with the frontend's progress-tracking components [2, 5].

**Core Fields:**
*   **`timestamp`**: ISO 8601 UTC timestamp of the event.
*   **`level`**: Severity indicator (`info`, `warning`, `error`, `milestone`).
*   **`stage`**: The model pipeline stage (e.g., `energy_solve`, `bridge_prep`, `mrio_impacts`).
*   **`message`**: Human-readable progress text for the UI.
*   **`payload`**: An optional structured JSON object (e.g., intermediate convergence metrics or the final `summary` result) [6].

---

## 8.3 Ingestion Logic (Worker Side)
The compute worker daemon acts as the primary producer of events by intercepting the mathematical model's execution stream [2].

1.  **Stdout Interception:** The worker daemon must capture the `stdout` and `stderr` of the `edim_model` subprocess in real-time [2, 7].
2.  **Parsing:** Structured lines emitted by the model CLI must be parsed as JSON and transformed into `runtime_event_v1` payloads [2].
3.  **Fast-Insert Persistence:**
    *   **Option A (PostgreSQL):** Execute high-frequency inserts into an `execution_events` table [2].
    *   **Option B (Azure Blob Storage):** Append every event to a dedicated **Append-Blob** (e.g., `logs/{execution_id}/runtime_events.jsonl`) [2].
4.  **Terminal Event:** Upon model completion, the worker must emit a final result event containing the `run_id` and the `summary` artifact payload to trigger the UI's transition to "Results Mode" [6].

---

## 8.4 Retrieval Boundary (API Side)
The FastAPI layer serves as the secure read boundary for the frontend [2].

*   **Endpoint:** `GET /api/executions/{execution_id}/events` [3, 8].
*   **Authorization:** The API must verify that the requesting user owns the run associated with the `execution_id` before querying the Event Store [5, 9].
*   **Isolation:** The API layer reads from the cloud persistence layer (DB or Blob) and streams the events to the client. The frontend **never** communicates directly with the worker or accesses worker-local log paths [2, 5].

---

## 8.5 Strategy for Staging and Production
*   **Shared Infrastructure:** Use the same PostgreSQL instance or Storage Account as defined in Chapters 3 and 4, utilizing logical isolation (table-level or container-prefix separation) [10, 11].
*   **High Performance:** Ensure the event table in PostgreSQL is indexed on `execution_id` and `timestamp` to support rapid, ordered polling by the UI.
*   **Fallback Reliability:** When in-memory worker state is unavailable (e.g., after a worker restart), the API must fall back to the Event Store as the durable record of what transpired during the run [12].

---

## 8.6 Best Practices for Implementation
*   **Buffer Management:** Implement a small internal buffer in the worker daemon to batch events if high-frequency logging (e.g., 100+ events per second) occurs, preventing database saturation.
*   **No Raw Logs:** Never expose raw model tracebacks or internal filesystem paths to the frontend. Ensure all errors are sanitized into user-facing `runtime_event_v1` messages [13].
*   **Order Preservation:** The `read_events` method must guarantee that events are returned in the exact chronological order they were produced to prevent the UI progress bar from jumping backward [5].


## 9.1 Report Generation Contract
The platform provides a mechanism to generate project-level analytical reports. While the current prototype implementation is basic, it serves as the stable backend linkage for future rich renderers.

### 9.1.1 The Report Artifacts
Every report generation task must produce two distinct files:
1.  **Markdown Report (`.md`):** A human-readable document containing project context and high-level summaries.
2.  **Source-Data JSON (`.source.json`):** A machine-readable file following the `edim_project_report_source_v1` schema. This file is the "source of truth" for future UI renderers [1, 2].

### 9.1.2 Data Aggregation Logic
The report engine must build the source-data JSON by aggregating the following inputs:
*   **Project Metadata:** Ownership, title, and geography.
*   **Selected Run Records:** Configuration and metadata for the specific runs chosen by the user.
*   **Run Summary Artifacts:** The engine must retrieve the `summary_json` artifacts from Blob Storage for every selected run to extract headline metrics [1, 3].
*   **Existing Export Records:** Metadata from previously generated project exports [1].

---

## 9.2 Project Export Bundles (ZIP Archives)
The platform allows users to export a full "workspace backup" that preserves enough provenance and data to interpret results offline.

### 9.2.1 Bundle Structure
The export service must initiate an asynchronous task to assemble a standardized directory tree and compress it into a ZIP archive:
*   `projects/`: Project-level metadata and configuration.
*   `runs/`: For every included run, its `request_bundle.json`, `integrated_results.json`, and other declared artifacts.
*   `datasets/`: Local copies of the specific dataset versions used by the exported runs to ensure reproducibility [4, 5].
*   `reports/`: (Optional) Included Markdown and source-data JSON files [1].
*   `provenance/`: Stable hashes of the normalized request, manifests, and artifact policies [6].

---

## 2.3 Storage Reference (`storage_ref`) Management
In the production environment, reports and exports are not stored as local files. Their metadata records in PostgreSQL must use **`storage_ref`** objects to track their physical location [7, 8].

*   **Schema:** The `storage_ref` object must contain:
    *   `provider`: (e.g., "azure_blob").
    *   `container`: The specific container (e.g., `prod-compiled-reports`).
    *   `object_key`: The unique path/filename within that container.
*   **Retrieval:** When the frontend requests a download via `/api/projects/{project_id}/reports/{report_id}/download`, the API resolves the `storage_ref` to a short-lived **SAS token URL** [7, 9].

---

## 9.4 Background Task Strategy
To maintain session continuity and prevent web-layer timeouts, report and export generation must be treated as asynchronous operations [3, 10].

1.  **Request:** The user triggers a report or export via POST.
2.  **Immediate Response:** The API creates the metadata record in a `queued` or `started` state and returns the ID immediately [11].
3.  **Task Execution:** The generation service (either within the App Service context or a separate background worker) assembles the files and uploads them to Azure Blob Storage [5, 12].
4.  **Completion:** Upon successful upload, the task updates the record status to `succeeded` and links the final `storage_ref`.
5.  **Frontend Interaction:** The UI polls the record status and enables the "Download" button only once the state is terminal.

---

## 9.5 Implementation Best Practices
*   **Offload Assembly:** For large project exports, perform the ZIP compression on ephemeral disk space (either the Worker VM or a transient App Service temp folder) before uploading to Blob Storage to avoid memory exhaustion [5].
*   **Stable Identifiers:** Use alphanumeric `report_id` and `export_id` descriptors for all public routes. Never expose internal container paths or object keys to the frontend [9].
*   **Provenance Integrity:** Ensure that every export bundle includes the `run_provenance` metadata to allow for exact scenario reproduction in the future [6, 13].


# Chapter 10: Frontend Integration & Compatibility Manifest

This chapter defines the technical requirements for deploying the React frontend and ensuring its reliable integration with the hosted Azure backend. The implementation must preserve the existing low-level transport boundaries while utilizing Azure-native delivery services and rigorous compatibility probing.

---

## 10.1 Frontend Delivery Service: Azure Static Web Apps (SWA)
The React frontend is transitioned from being served as static files by FastAPI to a dedicated, globally distributed delivery service.

*   **Strategy:** Use **Azure Static Web Apps (SWA)** to host the compiled React/Babel static bundle [1].
*   **Logical Isolation (Environments):**
    *   **Staging:** Utilize a **Preview Environment** triggered via CI/CD from the `staging` branch [1].
    *   **Production:** Utilize the **Production Environment** triggered from the `main` branch [1].
*   **Tier Requirement:** The **Standard Tier** is required to support custom domains, enterprise-grade authentication, and Private Link support [1].

---

## 10.2 Runtime Configuration & Environment Injection
The frontend must be able to switch between different backend targets without hardcoding URLs into the source code.

*   **Environment Variable:** The key configuration point is **`EDIM_BACKEND_API_BASE`** [1-3].
*   **Injection Logic:** This variable is injected at build time via the CI/CD pipeline. It must point to the **Staging API Slot** for staging builds and the **Production API Slot** for production builds [1, 4].
*   **Public Visibility:** This variable is a public API URL only; it must never contain credentials, API keys, or tenant secrets as it is loaded directly into the browser runtime [2, 5].
*   **Runtime Target Switch:** The UI header includes a toggle to switch between "Local" (same origin) and "Backend" (the hosted URL). Switching targets must clear the loaded workspace state and reload the session, projects, and catalogs from the selected API [2, 3, 5].

---

## 10.3 Compatibility Probing: `GET /api/system/manifest`
To prevent the UI from operating against an incompatible or misconfigured backend, the frontend must perform a **compatibility probe** before loading project data [5, 6].

### 10.3.1 The Manifest Contract
The backend must expose a stable `GET /api/system/manifest` endpoint that returns the `edim_system_manifest` schema [7, 8]. This manifest reports:
*   The `ok` status of the backend [7, 8].
*   List of all required **public endpoints** [7, 8].
*   Current runtime mode and artifact handoff settings [7, 9].

### 10.3.2 Frontend Compatibility States
Based on the manifest response, the frontend displays one of three states in the header [5, 6]:
*   **Contract ok:** The schema is correct, diagnostics are clean, and all required endpoints are listed [5, 6].
*   **Contract warning:** The backend is reachable, but one or more required endpoints are missing from the manifest [5, 6].
*   **Contract error:** The manifest is unreachable, has an incorrect schema, or reports failed diagnostics. Backend mode is disabled in this state [5, 6].

---

## 10.4 Preserving Transport Semantics (`api-client.js`)
The implementation must maintain the established low-level API client boundary to avoid breaking high-level workspace components.

*   **Boundary:** All low-level HTTP transport, upload calls, and download behavior must remain within **`frontend/api-client.js`** [10-12].
*   **Descriptor-Based Downloads:** The UI must continue to use alphanumeric descriptors (artifact IDs, report IDs) for all downloads. Components must **never infer filesystem paths** or internal storage keys [11, 13-15].
*   **Hash-Route Behavior:** The current hash-route pattern for landing, projects, and methodology pages must be preserved [11].
*   **Auth Provider Extension:** The API client includes a `window.EDIM_AUTH_PROVIDER` extension point. This must be used to inject the bearer-token or session headers required by the final Entra ID implementation without modifying the core dashboard components [16, 17].

---

## 10.5 CORS and Security Requirements
Since the frontend (hosted on SWA) and the backend (hosted on App Service) will reside on different domains, Cross-Origin Resource Sharing (CORS) must be configured correctly.

*   **Allowed Origins:** The backend must explicitly allow the origins of both the Staging and Production SWA instances [2, 8, 16].
*   **Allowed Methods/Headers:** The CORS policy must permit all standard HTTP methods (GET, POST, PATCH, DELETE) and headers used by the platform, including `Content-Type`, `Authorization`, and the transitional `X-EDIM-User-Id` [8, 16].
*   **Credentials:** If using session-based auth, ensure `Access-Control-Allow-Credentials` is handled appropriately.

---

## 10.6 Implementation Best Practices
*   **Stateless Frontend:** Ensure the React app remains a "platform shell" that does not store sensitive run data locally; all state should be re-hydrated from the backend upon target switching [10, 18].
*   **CORS Preflight:** Ensure the backend handles OPTIONS preflight requests efficiently to minimize UI latency [8, 16].
*   **Build Validation:** Use the existing `frontend/scripts/build-static.js` to validate the compact static bundle in `frontend/dist/` before deployment [12, 19].


# Chapter 11: Deployment, CI/CD & Smoke Test Acceptance

This final chapter defines the operational requirements for transitioning the platform into the UNDP Azure ecosystem. It specifies the target environment initialization sequence, the schema migration strategy, and the definitive 16-step smoke test that serves as the primary acceptance criterion for the productionization phase.

---

## 11.1 Target Environment Initialization
The deployment sequence requires the coordinated setup of resource groups and backing services before the application code is deployed [1].

1.  **Network Setup:** Provision a secure private virtual network (VNet) to house the PostgreSQL server and the Compute VM [1].
2.  **Persistence Layer:** Initialize the Azure Database for PostgreSQL flexible server within the private VNet [1].
3.  **Registry & Storage:** Instantiate the Azure Container Registry (ACR) for backend images and Azure Blob Storage with localized access controls [1].
4.  **Messaging:** Provision the Azure Service Bus namespace and create designated execution queues with custom lock durations and message expiration thresholds [1].
5.  **Compute:** Provision the Linux Azure Virtual Machine, configuring it for System-Assigned Managed Identity authorization to access the Service Bus [1].

---

## 11.2 Relational Schema Migration Strategy
Database integrity is maintained using the **Alembic** framework. Migrations must be executed transactionally and outside of the application's runtime loop [2].

*   **Execution Boundary:** The command `alembic upgrade head` must be triggered by automation tools **before** a new App Service container is permitted to start or accept incoming user traffic [2].
*   **Pipeline Integration:** This ensures that all tables, indexes, and constraints are successfully updated against the live Azure PostgreSQL instance before code changes go live [2].

---

## 11.3 Observability & Monitoring
The platform utilizes **Azure Monitor** and **Log Analytics** to centralize system-wide telemetries and performance baselines [3, 4].

*   **Structured Logging:** App Service containers, the VM background daemon, and the database engine must push structured log streams to a centralized Log Analytics workspace [3, 4].
*   **Alerting:** Real-time alerts must be configured for infrastructure failures, system overloads, database performance degradation, and queue backlogs [4].
*   **Diagnostic Segregation:** CONCEPTUAL errors (e.g., model convergence failures) are returned to users via the API, while technical failure contexts and raw tracebacks are written exclusively to the secure Log Analytics workspace [5].

---

## 11.4 The 16-Step Handoff Smoke Test
The primary acceptance criterion is the successful execution of the `backend/tools/backend_handoff_smoke.py` script against the hosted cloud environment [6, 7]. This test validates the entire project-owned, black-box model runtime contract [8, 9].

**The Mandatory Acceptance Sequence:**
1.  **GET /api/session:** Verify session and user context [10].
2.  **GET /api/system/manifest:** Verify contract identifiers and provider boundaries [10].
3.  **POST /api/projects:** Successfully create a new project [10].
4.  **GET /api/input-datasets:** Retrieve the dataset catalog [10].
5.  **GET /api/model-runtimes:** Verify artifact handoff and dataset staging modes [10].
6.  **POST /api/projects/{project_id}/runs/validate:** Pass environment setup validation [10].
7.  **POST /api/projects/{project_id}/runs:** Create a project run draft [10].
8.  **POST /api/projects/{project_id}/runs/{run_id}/submit:** Queue the execution via Service Bus [10].
9.  **Poll GET /api/executions/{execution_id}/status:** Track transition to terminal state [10].
10. **GET /api/executions/{execution_id}/events:** Stream real-time runtime events [10].
11. **GET /api/runs/{run_id}/artifacts:** List generated artifacts [10].
12. **Download summary_json:** Verify `artifact_publication` diagnostics [10].
13. **Download Result Artifacts:** Retrieve `integrated_results_json` and `results_csv` via artifact IDs [10].
14. **POST /api/projects/{project_id}/reports:** Generate and download a project report [10].
15. **POST /api/runs/{run_id}/export:** Download a single-run export bundle [10].
16. **POST /api/projects/{project_id}/exports:** Download a full project workspace backup [10].

---

## 11.5 Operational Handoff Rules
*   **Contract Invariance:** Do not modify the backend route logic or public OpenAPI schemas during the migration; replace only the infrastructure providers [11, 12].
*   **Provenance Retention:** Ensure every executed model run preserves the `run_provenance` object (with stable hashes for configuration, manifest, and datasets) to allow for exact reproduction [13, 14].
*   **Descriptor Integrity:** All UI downloads (Artifacts, Reports, Exports) must remain descriptor-based. Frontend components must **never** be updated to infer filesystem paths or internal storage keys [13, 15].

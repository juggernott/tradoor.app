# Customer-hosted research runner

The offline runner keeps private code, dataset and report on the customer's
machine. It has no upload or cloud telemetry client. Cloud synchronization,
factor mining/import, remote scheduling and customer-hosted live execution are
not implemented. The output report can itself reveal alpha; do not publish it
automatically.

## Restricted container

Build with `docker compose -f deploy/runner.compose.yaml build`.
Set TRADOOR_RUNNER_INPUT, TRADOOR_RUNNER_SOURCE and TRADOOR_RUNNER_OUTPUT to
separate existing private directories. Input contains prices.csv (the current
daily date,symbol,close format) and config.json (the current bounded baseline
configuration). Output must be a dedicated empty directory writable by UID
10001. Source contains the private adapter dependencies; v12 uses its private
research/lib tree. Set TRADOOR_RUNNER_FACTORY explicitly, for example
alphaloop.web.alphacore_v12:create_engine for the owner's private v12 baseline.
Other adapters must be installed in a customer-specific image; don't bake them
into a shared public image.

Run `docker compose -f deploy/runner.compose.yaml run --rm research`.
The runtime has no network, no provider keys, no Docker socket or host services,
a read-only root and source/input mounts, non-root UID, dropped capabilities,
no-new-privileges, PID/memory/CPU limits and a bounded temporary filesystem.
Only the dedicated report directory is writable on the host. The build context
is allowlisted to public package files. Fetch licensed datasets in a separate
trusted process before running research; do not enable runner networking to
fetch them. Keep stdout/stderr private as customer code can write to them.

Containers are a defense layer, not a guarantee against malicious native code
or kernel vulnerabilities. Production hosting requires isolated customer OS
accounts/VMs, restricted file permissions, image digest pinning and scanning,
wall-clock deadlines with forced container cleanup, output quotas, patching and
escape/egress tests. The manifest is not permission to run arbitrary uploaded
code on the shared web host.

Compose configuration validation passed on the development laptop. The Docker
Linux daemon was unavailable, so image build, runtime restrictions and escape
tests have not been verified. The native runner has automated tests; native
execution is trusted local execution and supplies no OS sandbox.

## Login and current library

The current development dashboard is http://127.0.0.1:4173 and needs no login
because it binds only to loopback. Named deployed workspaces require the owner
token configured for that workspace, exchanged for a secure session over HTTPS.
Public tradoor.app hosting and user registration are not deployed.

Factor research now lists completed backtest strategies from the current
workspace and explicitly marks the mined-factor catalog as not imported. It
does not turn demo baselines into mined factors, or expose the owner's private
production roster to customers. Tradoor independently implements the workflow;
it does not contain Quandora's private backend or database.

## Historical data and provenance

The current dashboard accepts close-price panels only. The legacy Glassnode
adapter covers three metrics; CryptoQuant remains a skeleton. Neither is a
working dashboard feature input yet. Provider history and resolution depend on
the customer's entitlement. Historical revisions and publication timestamps
must be validated before treating on-chain series as point-in-time backtests.

Use descriptive metric labels such as Market value / realized value ratio,
Spent-output profit ratio, Active addresses, Exchange reserves or Miner flows.
Preserve provider, endpoint, timestamps, revision and license metadata in the
private data catalog. Preserve any attribution required on displayed/exported
data. Renaming does not grant redistribution rights. Do not redistribute the
owner's paid datasets or credentials into customer workspaces. Customer-local
licensed data or a separately authorized commercial agreement is required;
customer-local execution alone does not grant commercial rights.

References checked 19 October 2026:
- https://docs.glassnode.com/basic-api/api
- https://studio.glassnode.com/terms-and-conditions
- https://cryptoquant.com/apis
- https://www.cryptoquant.com/data-distribution-policy

No provider historical dataset was fetched, relabeled or distributed by this change.

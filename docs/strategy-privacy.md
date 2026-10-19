# Engine and private alpha boundary

Tradoor is reusable execution and research infrastructure. A user's factors,
strategy code, parameters, signals, holdings and results are private workspace
assets. They are not platform defaults, community content or reusable training
data. Publication must be a separate explicit owner action. There is currently
no publication endpoint.

## Implemented boundary

- API, persistence, scheduling, market validation and simulated accounting are
  engine infrastructure. They do not contain the owner's production strategies.
- `baseline_strategy.py` is a public demonstration ranking policy, separate from
  that infrastructure. The v12 adapter connects a reviewed private library to
  this explicitly selected baseline. It does not load the production roster.
- Private source is outside the public checkout and build archive. Only an
  operator-selected adapter is imported; requests cannot select Python imports
  or submit executable strategy code. Static serving is limited to `web/dist`.
- The current installation is one owner's trusted workspace: one database,
  private adapter and worker. Configurations, signals, positions, trades and
  results returned by workspace APIs are sensitive and visible to that owner.
  Source code is not returned, but results can still reveal alpha.
- Private directory ignore rules are a backstop, not an isolation control. Keep
  customer packages outside the repository and verify release contents.

## Required before onboarding other users

The current global adapter, owner token and SQLite workspace must never be
shared between unrelated customers. The application is not yet a multi-user
service. Do not advertise tenant isolation or deploy this single-owner backend
as a shared customer workspace.

Each customer needs an authenticated identity and authorization on every read,
write, export, job and worker action. Tenant scope must come from the verified
session, not a caller-provided owner ID. Use isolated private storage, keys,
strategy packages, worker processes and caches; never use the current global
adapter cache for unrelated customer strategies. Queue claims and result writes
must retain tenant identity. Verify cross-tenant access denials, including
guessed IDs, exports, errors, logs, caches and background jobs, before launch.

Private strategy execution must use a restricted runner with resource limits,
network controls and isolated secrets; do not import arbitrary customer Python
into a shared API process. Sharing engine infrastructure does not authorize
sharing source, parameters, derived signals or research results.

For users who do not want the hosting operator to receive their alpha, provide
a customer-hosted runner that keeps code and research data in their environment.
Send only the minimum explicitly authorized output to Tradoor. Hosted execution
alone cannot promise secrecy from the operator; encryption at rest does not
change that trust boundary. Neither runner mode is implemented yet.

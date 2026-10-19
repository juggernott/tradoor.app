# Owner-supplied historical data

The Data library shows an operator-provisioned catalog. Customers can import
only explicitly granted daily price panels into their private workspace and
use them in backend backtests. Strategy code, signals and private production
rosters are not part of the data catalog.

Set `TRADOOR_DATA_CATALOG` to a private JSON manifest. Local development defaults
to ignored `state/data-catalog.json`. Named workspace manifests can optionally
set `data_catalog`; omission clears inherited catalog configuration. The scope
comes from the process's bound workspace identity, never an API parameter.

```json
{
  "datasets": [{
    "id": "daily-price-panel-v1",
    "label": "Daily closing prices",
    "description": "Approved daily price history",
    "kind": "daily-prices",
    "file": "panels/prices.csv",
    "sha256": "SHA256_OF_EXACT_FILE_BYTES",
    "workspaces": ["customer-a"],
    "customer_use_approved": false,
    "rights_reference": "Private reference to applicable customer-use agreement",
    "attribution": "Required attribution from that agreement"
  }]
}
```

Default to unapproved. Enable only after the operator establishes rights for the
specific use and audience. This flag is an operational gate, not proof of legal
rights. Descriptive labels do not change licensing or remove attribution duties.
Never grant the development-owner dataset to unrelated customers by default.

Files must reside beneath the catalog's directory, match their SHA-256 hash,
stay below 5 MB and pass the daily CSV panel validator. Source paths and private
rights references are omitted from listings. Missing/denied IDs return 404.
Import preserves required attribution and catalog identity. Imported copies
remain in the customer's database if a grant is later revoked; revocation is
prospective and does not recall copies. Backups, expiry and contractual deletion
procedures need a separate retention implementation.

Verified locally: imported 600 common daily BTC/ETH observations from the
owner's existing exchange archive into the owner's private workspace. No
third-party customer grant or paid-provider dataset was enabled. Private files
and the catalog manifest are excluded from Git.

Current scope is daily close prices. Glassnode/CryptoQuant feature panels,
historical publication/revision metadata, point-in-time joins, factor mining,
cloud deployment, user registration and container runtime verification remain
unfinished. This catalog does not turn those archives into valid backtest inputs.

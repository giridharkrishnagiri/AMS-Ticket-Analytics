# Dashboard Filter Cache

The live dashboard uses a two-path filter model so filter dropdowns stay usable with large data volumes.

`dashboard_filter_catalog` stores the static filter catalog for Applications and Volumetrics. The UI reads this table first, so available filter values and baseline counts can render immediately without waiting for cascading counts.

`dashboard_filter_facts` stores narrow indexed filter facts. Applications facts are built from Application Inventory. Volumetrics facts are built only from generic ticket records: in-scope Incidents/SC Tasks from `tickets` and out-of-scope Incidents/SC Tasks from `assessment_out_of_scope_tickets`. Problem and Change records are excluded.

`dashboard_filter_cache_status` tracks whether each dashboard area cache is missing, ready, stale, refreshing, or failed.

Manual refresh is available from Maintenance under Dashboard Filter Cache:

- Refresh Applications Filter Cache
- Refresh Volumetrics Filter Cache
- Refresh All Filter Caches

Data-changing upload, mapping, application-inventory, and maintenance-reset flows mark the cache stale. Refreshing the cache rebuilds facts and catalog values. The filter cache APIs do not return raw tickets, raw SLA/OLA rows, `normalized_payload`, or `cmdb_payload`.


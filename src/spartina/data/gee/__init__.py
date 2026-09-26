"""Google Earth Engine interfaces (M0 skeletons).

These modules define contracts only. No network calls happen at import;
real GEE access is enabled by locally configured credentials (never stored
in Git) and is exercised exclusively through integration tests marked
``gee_integration``.
"""

"""SelfScope analysis engine: trends, cross-app correlations, period comparisons, anomalies.

Pure Python + pandas / numpy / scipy / scikit-learn: runs in Pyodide (browser) and CPython
(tests). Input is the daily_features view (one row per day); see docs/analysis.md.
"""

ENGINE_VERSION = "4"

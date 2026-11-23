"""SelfScope ML code shared between offline training (ml/) and the browser (Pyodide).

features.py and rules.py are pure Python (+ the standard library) so they run unchanged
in both places. web/src/python/selfscope_ml/ is a byte-identical copy made by
web/scripts/sync-ml.mjs; edit the files here, never the copy.
"""

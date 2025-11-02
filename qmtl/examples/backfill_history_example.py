import importlib
_module = None

def __getattr__(attr):
    global _module
    if _module is None:
        _module = importlib.import_module('qmtl.examples.utils.backfill_history_example')
    return getattr(_module, attr)

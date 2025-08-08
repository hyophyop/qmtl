import importlib
_module = None

def __getattr__(attr):
    global _module
    if _module is None:
        _module = importlib.import_module('qmtl.examples.strategies.recorder_strategy')
    return getattr(_module, attr)

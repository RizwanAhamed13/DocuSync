from importlib import import_module as _import_module

# Load the actual application package located at quad.app
_app = _import_module('quad.app')

# Export its attributes at the top-level app package
globals().update(_app.__dict__)

__all__ = getattr(_app, '__all__', [])

"""DevOps Toolbox - click-based, allowlisted DevOps operations (backend shared by the desktop window and the local web app).

Nothing here accepts a free-form command: every operation is implemented in this package, validates its own parameters and
builds an argument list (never a shell string) for `subprocess`.  See README.md."""
__version__ = "0.1.0"

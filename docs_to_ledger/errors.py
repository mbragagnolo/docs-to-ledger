class DocsToLedgerError(Exception):
    """Base class for all docs-to-ledger errors."""


class ConfigError(DocsToLedgerError):
    """Raised when the config file is missing, unreadable, or invalid."""


class OcrUnavailableError(DocsToLedgerError):
    """Raised when Tesseract is required but not installed/on PATH."""


class OutputWriteError(DocsToLedgerError):
    """Raised when the output directory is not writable or a workbook is locked."""

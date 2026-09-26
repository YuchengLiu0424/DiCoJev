"""Typed component-boundary failures."""


class DiCoJevError(Exception):
    """Base project error."""


class ConfigurationError(DiCoJevError):
    """Configuration cannot instantiate the requested component."""


class GeneratorUnavailable(DiCoJevError):
    """Candidate generation service failed or timed out."""


class BackendUnavailable(DiCoJevError):
    """Decision service failed or timed out."""


class MalformedProviderResponse(DiCoJevError):
    """A provider response cannot be normalized safely."""


class CapabilityMismatch(DiCoJevError):
    """A component cannot consume the requested state modality natively."""


class BudgetExhausted(DiCoJevError):
    """A configured latency, compute, round, or candidate budget is exhausted."""

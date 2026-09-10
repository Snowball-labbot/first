from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    CONFIG = 2
    GATE_FAILED = 3
    INTEGRITY = 4
    BLOCKED = 5
    INTERNAL = 6
    ENVIRONMENT = 7
    UNTRUSTED = 8


class MMFlowError(RuntimeError):
    exit_code = ExitCode.INTERNAL


class ConfigError(MMFlowError):
    exit_code = ExitCode.CONFIG


class EvidenceInsufficientError(MMFlowError):
    """A stage check failed on business evidence content, not on internal state.

    Gate classification: FAIL.  This is the ordinary "the evidence does not
    satisfy the requirement" case, distinct from Registry/policy/hash
    corruption which must surface as ERROR.
    """

    exit_code = ExitCode.GATE_FAILED


class GateFailedError(MMFlowError):
    exit_code = ExitCode.GATE_FAILED


class IntegrityError(MMFlowError):
    exit_code = ExitCode.INTEGRITY


class BlockedError(MMFlowError):
    exit_code = ExitCode.BLOCKED

    def __init__(self, message: str, block_payload: dict | None = None) -> None:
        super().__init__(message)
        self.block_payload = block_payload


class EnvironmentError(MMFlowError):
    exit_code = ExitCode.ENVIRONMENT


class UntrustedArtifactError(MMFlowError):
    exit_code = ExitCode.UNTRUSTED

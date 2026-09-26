"""
Broker interpretation engine.

The core reframe: a broker is a declarative BrokerSpec (data), which the compiler
turns into an executable Job (produce-a-job), which an executor runs
(execute-a-job). No broker-specific logic lives in the core.

Public API:
    BrokerSpec, Step, EmailSpec   — the declarative description format
    compile_job                   — BrokerSpec + member -> Job
    Job, JobStep, EmailJob        — the compiled, serializable job
    DryRunExecutor                — run a job with no I/O (testing / validation)
    PlaywrightExecutor            — real executor skeleton (browser, validated in Docker)
    ExecResult                    — uniform execution result
"""

from .broker_spec import BrokerSpec, Step, EmailSpec, SPEC_VERSION, KNOWN_FIELDS, STEP_KINDS
from .compiler import compile_job, Job, JobStep, EmailJob, CompileError
from .executor import JobExecutor, DryRunExecutor, PlaywrightExecutor, ExecResult

__all__ = [
    "BrokerSpec", "Step", "EmailSpec", "SPEC_VERSION", "KNOWN_FIELDS", "STEP_KINDS",
    "compile_job", "Job", "JobStep", "EmailJob", "CompileError",
    "JobExecutor", "DryRunExecutor", "PlaywrightExecutor", "ExecResult",
]

"""Independent release, workflow, schema and policy responsibilities."""
from . import __version__
PRODUCT_VERSION = __version__
WORKFLOW_VERSION = "pmrs.workflows/final-1"
SCHEMA_VERSION = "pmrs.project/3.4-final-1"
OBJECT_SCHEMA = "pmrs.knowledge-record/1"
TASK_SCHEMA = "pmrs.task/final-1"
RESPONSE_SCHEMA = "pmrs.response/final-1"
POLICY_VERSION = "pmrs.assurance-policy/2"
COMMIT_SCHEMA = "pmrs.commit/final-1"
VERSIONS = {"product": PRODUCT_VERSION, "workflow": WORKFLOW_VERSION,
            "schema": SCHEMA_VERSION, "policy": POLICY_VERSION}

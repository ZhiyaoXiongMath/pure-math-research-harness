"""Independent release, workflow, schema and policy responsibilities."""
from . import __version__
PRODUCT_VERSION = __version__
WORKFLOW_VERSION = "pmrs.workflows/4.2.2"
from pmrh.adapters.storage.native_format import SCHEMA_VERSION as SCHEMA_VERSION
OBJECT_SCHEMA = "pmrs.knowledge-record/1"
TASK_SCHEMA = "pmrs.task/4.2.2"
RESPONSE_SCHEMA = "pmrs.response/4.2.2"
POLICY_VERSION = "pmrs.assurance-policy/2"
from pmrh.adapters.storage.native_format import COMMIT_SCHEMA as COMMIT_SCHEMA
VERSIONS = {"product": PRODUCT_VERSION, "workflow": WORKFLOW_VERSION,
            "schema": SCHEMA_VERSION, "policy": POLICY_VERSION}

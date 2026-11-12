"""Azure integration scenario skeletons: never simulate cloud outcomes."""

import os
import pytest

REASON = "Azure APIM URL, Entra tokens, and deployed POC prerequisites are absent; outcomes must not be faked."
pytestmark = pytest.mark.skipif(not os.getenv("APIM_BASE"), reason=REASON)

@pytest.mark.parametrize("scenario", [f"S{i:02d}" for i in range(1, 17)])
def test_approved_scenario_requires_deployed_azure_prerequisites(scenario):
    pytest.fail(f"{scenario} skeleton must be replaced with a real deployed scenario invocation")

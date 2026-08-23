from agent_guardian.agent import app
from agent_guardian.utils.token_utils import TokenSafetyPlugin
from agent_guardian.utils.resilience import GlobalResiliencePlugin, ErrorAwareReflectAndRetryToolPlugin


def test_app_plugins_registered():
    """Verify that expected plugins are registered on the ADK App."""
    token_plugins = [p for p in app.plugins if isinstance(p, TokenSafetyPlugin)]
    assert len(token_plugins) == 1, "TokenSafetyPlugin should be registered."

    resilience_plugins = [p for p in app.plugins if isinstance(p, GlobalResiliencePlugin)]
    assert len(resilience_plugins) == 1, "GlobalResiliencePlugin should be registered."

    reflect_plugins = [p for p in app.plugins if isinstance(p, ErrorAwareReflectAndRetryToolPlugin)]
    assert len(reflect_plugins) == 1, "ErrorAwareReflectAndRetryToolPlugin should be registered."

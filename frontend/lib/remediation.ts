// Sentinel messages for the Human-in-the-Loop remediation approval flow.
// Sent as the message text via run_sse when the user clicks Approve / Skip on a
// pending remediation; the agent's supervisor routes them to the resume flow.
// Keep in sync with REMEDIATION_APPROVE_CMD / REMEDIATION_SKIP_CMD in
// agent_guardian/agent.py.
export const REMEDIATION_APPROVE_CMD = "__AG_APPROVE_REMEDIATION__";
export const REMEDIATION_SKIP_CMD = "__AG_SKIP_REMEDIATION__";

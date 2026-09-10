"""A fixed authenticated catalog selection for provider-free tests."""

from llm_agent_kernel import ProviderConfiguration
from llm_agent_kernel.fakes import InMemoryModelDecisionJournal
from provider_runtime.agent_runtime import CredentialRef


def frozen_provider(
    profile_key: str = "jarvis-test",
    model: str = "gpt-5.6-terra",
    reasoning: str = "high",
) -> ProviderConfiguration:
    return ProviderConfiguration(
        auth=CredentialRef("local_account", profile_key),
        model_key=model,
        reasoning=reasoning,
        agent_definition_revision="test-catalog-v1",
        row_fingerprint="a" * 64,
    )


def decision_key(scope: str, ordinal: int) -> str:
    import hashlib

    return hashlib.sha256(f"{scope}:{ordinal}".encode()).hexdigest()


def model_journal(evidence: object) -> InMemoryModelDecisionJournal:
    del evidence
    return InMemoryModelDecisionJournal()

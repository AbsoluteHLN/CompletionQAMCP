# Using the writing workflow

The agent should produce a concrete polished draft, not stop at diagnostics.

1. Choose conversation_summary, technical_document or academic and retain the original document/revision. Use the current host model only within the user's authorized writing task. No new API account or key is required by the plugin.
2. Ask that host model for a revised candidate: result-first concise prose for summaries; consistent terminology and clear operational structure for technical writing; logical progression with preserved evidence and necessary limitations for papers.
3. Return both original and candidate. Run `python -m completion_plugin.cli text original.txt --profile academic --candidate candidate.txt` to get change spans, structure diagnostics and protected-content comparisons. The CLI does not itself call a model.
4. In an integrated host, PolishingSession.run uses HostBindings.generate for the actual candidate. Its trusted authorize callback binds the full request. Optional semantic_review is a separate reviewer invocation with a separate identity; absent review is clearly not_run. Synthetic bindings must declare execution_kind=mock.
5. Inspect factual changes: numbers, units, cited sources, equations, negation, causal claims and essential limitations. Ordinary sentence restructuring within the user's requested editing scope does not need sentence-by-sentence approval. Suspicious factual changes should be corrected or explicitly reviewed.
6. PolishingSession.adopt binds the unchanged original, current revision, candidate and full audit report. It returns the accepted draft for use; it does not overwrite files or certify the final project complete. A changed original requires a fresh run.

No real host provider was called in this environment. The candidate-generation interface is runnable with a configured trusted host; the installed Skill can guide an existing agent to generate candidates and run the local comparison now. Rule checks neither prove factual truth nor replace semantic editorial judgment.

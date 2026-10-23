"""ClawBack evaluation: a synthetic labelled test set and the harness that scores the pipeline on it.

    python -m evals.run --models off     # rules only, no key, no network
    python -m evals.run --models on      # live Nemotron tiers as the pipeline uses them

The data in evals/data is synthetic (see evals/data/README.md). Nothing here changes product code.
"""

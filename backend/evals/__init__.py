"""ClawBack evaluation: a synthetic labelled test set and the harness that scores the pipeline on it.

    python -m evals.run --models off                   # rules only, no key, no network
    python -m evals.run --models on                    # live Nemotron tiers as the pipeline uses them
    python -m evals.run --set holdout --models both    # the held-out set instead of the main one

The data in evals/data (main) and evals/holdout (held out, never used to tune the product) is synthetic (see each
folder's README.md). Nothing here changes product code.
"""

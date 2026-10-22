"""The funnel: cheap steps on everything, expensive models only on the few items that need them.

    bank transactions --> recurring.py --+
                                         +--> usage.py --> value.py --> flags.py --> dashboard
    emails --> triage.py --> extract.py -+
                                                    recommend.py / cancel.py run only when the user asks.
"""

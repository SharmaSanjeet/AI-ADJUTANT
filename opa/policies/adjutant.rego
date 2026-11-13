package adjutant

# The containment policy gate (Allow / Deny / Escalate) is implemented
# deterministically in src/adjutant/containment.py and is the source of truth:
# every decision it records is reproducible from the same inputs and is covered
# by the audit chain. This sidecar stays for a future phase where policy may be
# externalised; until then it defaults to escalate, which can never approve or
# execute anything.
default decision := "escalate"

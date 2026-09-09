# Configuration and fixed model assumptions

The confirmatory run is controlled by `configs/cluster.json`. Values that alter
training, evaluation, search, or statistical aggregation are stored in that
file and therefore included in its SHA-256 configuration hash.

## Confirmatory parameters

| Field | Purpose |
|---|---|
| `protocol_name` | Identifies the frozen protocol and activates strict provenance checks. |
| `training_episodes` | Q-learning episodes for each independently trained responder. |
| `evaluation_policy_seeds` | Defines both the independent policies and the Slurm array size. |
| `horizon` | Closed-loop cycles in every campaign execution. |
| `audit_lead` | Number of cycles before physical impact at which the response is explained. |
| `search_depth` | Maximum number of campaign edits in one search path. |
| `beam_width` | Candidates retained at each guided-search depth. |
| `search_evaluation_budget` | Maximum simulator calls for each campaign-space method. |
| `minimum_impact_gain` | Required candidate-minus-factual physical impact. |
| `responder_learning_rate` | Tabular Q-learning step size. |
| `responder_discount` | Q-learning future-reward discount. |
| `response_costs` | Ordered costs for monitor, inspect, restrict, and backup. |
| `switching_cost` | Cost of changing response action between cycles. |
| `seed_offsets` | Disjoint training, scenario, and transfer random streams. |
| `bootstrap_seed` | Reproducible paired-bootstrap stream. |
| `scenarios` | Names, timing offsets, impact targets, magnitudes, and visibility scales. |

The Slurm array range is derived from `evaluation_policy_seeds`. CPU memory,
wall time, and maximum simultaneous tasks are operational settings exposed as
`CFRT_MEMORY`, `CFRT_WALLTIME`, and `CFRT_MAX_CONCURRENT`; they do not change the
scientific configuration.

## Fixed method definitions

Constants that define the studied system remain in source control rather than
being silently tuned per run:

- `core/campaign.py` defines the six-stage campaign grammar, legal assets,
  prerequisite graph, and edit operators;
- `core/topology.py` defines the directed commissioned conduits and privilege
  transitions;
- `models/plant.py` defines the three-stage process equations, reference and
  perturbed integration models, and asset-specific attack effects;
- `models/responder.py` defines the observation encoder and ordered response
  interface.

These are model assumptions, not values selected after observing confirmatory
results. Changing one requires a new protocol name because the Git commit and
configuration hash together identify the complete experiment.

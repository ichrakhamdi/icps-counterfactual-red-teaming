# Experimental Protocol

## Units of analysis

The primary unit is one factual campaign and its selected counterfactual under
one frozen responder seed. Training seeds, scenario-development seeds, and
confirmatory evaluation seeds must be disjoint.

## Baselines

1. **Random-valid:** samples edits from the same valid edit set without using
   responder or impact feedback.
2. **Feature-CF:** changes observed features directly to flip the response;
   because it has no campaign generator, cyber and physical executability are
   reported as false rather than inferred from feature ranges.
3. **Cyber-CF:** searches only candidates satisfying campaign prerequisites and
   timing; neither its frontier nor its final selection uses closed-loop
   physical impact.
4. **Cyber-physical CF:** the complete proposed method.

## Primary metrics

- Target validity: fraction selecting a weaker response in the audit window.
- Cyber feasibility: fraction of returned explanations accepted by the
  independent campaign validator.
- Physical validity: fraction of returned explanations producing finite,
  bounded process trajectories under both execution configurations.
- Impact gain: counterfactual minus factual maximum band deviation; a result is
  impact-valid only when it meets the configured minimum gain.
- Edit cost: normalized visibility, timing, duration, and intensity changes.
- Search cost: number of simulator executions and wall-clock time.
- Proposal diagnostics: generated, validator-rejected, and duplicate campaign
  candidates, reported separately from simulator evaluations.
- Transfer validity: fraction preserving target validity in high-fidelity mode.

## Statistical analysis

- Report medians and interquartile ranges across policy--scenario units.
- Report paired mean validity-rate differences with bootstrap intervals,
  resampling independent policy seeds rather than correlated scenarios.
- The artifact computes descriptive medians, interquartile ranges, and paired
  bootstrap intervals. Null-hypothesis tests will be added only if the final
  paper retains claims that require them.
- Treat all pilot results as descriptive.

## Six-page ablations

- remove physical-impact selection (`Cyber-CF`);
- replace guided beam ordering with matched-budget random-valid search;
- compare direct feature perturbation with executable campaign edits;
- report search-budget sensitivity using the fixed local and cluster budgets.

## Leakage controls

No confirmatory scenario may be used during responder training or search-operator
development. The paper must report the number of invalid candidates rather than
silently discarding them.

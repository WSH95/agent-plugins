# Curated Experimental Evidence

<!-- THE RULE (non-negotiable):
     Every quantitative statement in the paper must trace to an evidence row
     here (tag it in the .tex source as a comment: % evidence: E3), and every
     row must trace to a raw source (log file, W&B run, notebook, video, robot
     trial sheet, or an author-confirmed value). Agents may reformat this file
     but must never invent, extrapolate, or "reasonably estimate" values. -->

## Evidence profiles

Tag each row with the profile whose reporting standards apply:

- `deep_rl_legged` — **default** for deep RL / robot learning / legged
  locomotion results (rliable-style reporting, below).
- `control_planning` — model-based control, MPC, planners.
- `perception` — detection/estimation/mapping components.
- `hardware_systems` — real-robot system trials and deployments.
- `hri_user_study` — human-subject studies.
- `generic_robotics` — anything else; state the standard used in Notes.

## Result table

| ID | Claims | Profile | Experiment / condition | Metric (dir.) | Value | Uncertainty & aggregation | Train seeds | Eval eps/trials | Source | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | C1 | deep_rl_legged | ours vs. blind baseline, rough-terrain suite (sim) | success rate (↑) | 0.87 | IQM, 95% stratified bootstrap CI [0.83, 0.90] | 10 | 100 eps/seed/terrain | `logs/run_042/` | example row — replace |
| E2 | C2 | hardware_systems | Go2 outdoor gravel course, ours | falls per 10 trials (↓) | 1 | exact count | n/a (1 deployed policy) | 10 trials x 30 m | `logs/hw_sheet_03.csv` + video | example row — replace |

## Default reporting standard: `deep_rl_legged`

Follow Agarwal et al., *Deep Reinforcement Learning at the Edge of the
Statistical Precipice* (NeurIPS 2021, https://arxiv.org/abs/2108.13264;
code: https://github.com/google-research/rliable). This is the default for
robot-learning results in this project — **not** a universal standard for all
robotics papers (see profile notes below).

- **Aggregate**: prefer IQM (optionally also median/mean) with 95% stratified
  bootstrap CIs when aggregating across seeds/tasks/terrains; use performance
  profiles when comparing >= 2 methods across >= 3 tasks/terrains; consider
  probability of improvement for matched comparisons. Never rest a claim on a
  single point estimate.
- **Units of variation — never conflate**: training seeds != evaluation seeds
  != episodes/rollouts != terrains/tasks != hardware trials. **Rollouts from
  one trained policy are NOT independent training seeds**; N episodes of one
  policy is a sample size of 1 at the seed level.
- **Checkpoint policy**: predeclare and record it here (final checkpoint /
  best-validation / average of last K / other). Post-hoc checkpoint picking is
  cherry-picking.
- **Completeness**: record failed seeds, diverged runs, safety aborts, and any
  exclusions with reasons (in Notes or the caveats section).
- **Baseline fairness** (state per comparison): same observations and
  privileged information, same action space, same terrain curriculum and
  domain randomization, same command distribution, comparable compute and
  tuning budget. Undisclosed asymmetries invalidate the comparison.
- **Legged-robot metrics where applicable**: success rate, fall rate, distance
  traveled, command/velocity/yaw tracking error, cost of transport or energy,
  torque/jerk smoothness, foot slip, perturbation recovery, control frequency
  and latency, safety interventions, sim-to-real transfer success.
- **Real-robot trials additionally record**: platform, terrain, trial count
  and duration/distance, battery/payload condition if relevant, operator
  interventions, safety stops.

## Other profiles (one-line standards)

- `control_planning`: tracking/trajectory error, constraint violations,
  collision rate, solve time and latency distribution, success/failure
  taxonomy; state solver settings and horizon.
- `perception`: dataset and split, metric definitions, calibration,
  precision/recall or task-standard metrics, cross-dataset generalization,
  failure modes.
- `hardware_systems`: trial counts, environments, intervention rate, failure
  taxonomy, runtime, power/thermal constraints.
- `hri_user_study`: N participants, within/between-subjects design,
  statistical test and effect size, preregistration if any, ethics/IRB status.

## Anti-patterns (rows exhibiting these will be flagged in review)

- Reporting only the best seed, or silently dropping failed seeds.
- Treating episodes/rollouts of one policy as independent seeds.
- Mixing simulation and real-robot trials in one aggregate without saying so.
- Comparing against baselines with different observations/action spaces or
  privileged information without disclosure.
- Claiming "robustness" from a single noise level or terrain condition.
- "Significant" without a test, CI separation, or effect size.

## Notes and caveats

- (excluded runs and why, anomalies, hardware/config differences, missing
  statistical tests, known reviewer-risk items)

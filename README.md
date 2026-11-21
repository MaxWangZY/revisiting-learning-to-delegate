# Revisiting Learning to Delegate: LLM Discovered Heuristics for Large-Scale Vehicle Routing

This repository contains the exact Python source for three delegation policies evaluated in the companion manuscript by Zhengyang Wang, Renfei Tan, Shuze Daniel Liu, and David Simchi-Levi. The manuscript is in preparation.

A delegation is a group of current vehicle routes whose customers a repair solver can reroute together. Each policy forms and orders these groups for a capacitated vehicle routing problem (CVRP).

## Evaluated policies

| File | Role in the study |
| --- | --- |
| [policy135.py](policies/policy135.py) | Primary policy, ranked first on validation |
| [policy143.py](policies/policy143.py) | Exploratory policy, ranked second on validation |
| [policy147.py](policies/policy147.py) | Exploratory policy, ranked third on validation |

Policies 143 and 147 were included as exploratory comparisons after the transfer results were inspected.

## Policy interface

Each file implements `choose_delegations(problem, state, history, limits)` using the Python standard library.

- `problem` provides customer coordinates and demands, vehicle capacity, and the depot ID.
- `state` provides current routes, solution cost, iteration, and customer selection statistics.
- `history` records completed repair attempts and starts empty.
- `limits` specifies the maximum number of delegations and the maximum route and customer counts per delegation.

The function returns a list of delegations in priority order. Each delegation contains indices into `state.routes`. The evaluation harness calls LKH or HGS to repair the chosen groups and checks the resulting routes. The full evaluation pipeline and result files are planned for release with the final publication.

## License

The policy source is licensed under the [MIT License](LICENSE).

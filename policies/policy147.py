from math import sqrt


def _blocks(route, demands, distances, depot):
    n = len(route)
    path = (depot,) + route + (depot,)
    cumulative = [0.0]
    for customer in route:
        cumulative.append(cumulative[-1] + demands[customer])

    blocks = []
    for length in (1, 2, 3):
        if length > n:
            continue
        positions = n - length + 1
        if length == 1:
            starts = list(range(positions))
        else:
            selected = set()
            samples = min(5, positions)
            for k in range(samples):
                selected.add(k * (positions - 1) // max(1, samples - 1))

            cursor = 0
            for quarter in (1, 2, 3):
                target = cumulative[-1] * quarter / 4.0
                while cursor + 1 < n and cumulative[cursor + 1] < target:
                    cursor += 1
                start = cursor - (length - 1) // 2
                selected.add(max(0, min(positions - 1, start)))
            starts = sorted(selected)

        for start in starts:
            end = start + length
            first = route[start]
            last = route[end - 1]
            before = path[start]
            after = path[end + 1]
            internal = 0.0
            for k in range(start, end - 1):
                internal += distances[route[k]][route[k + 1]]
            removed = (
                distances[before][first]
                + internal
                + distances[last][after]
                - distances[before][after]
            )
            blocks.append((
                start, end, first, last,
                cumulative[end] - cumulative[start],
                internal, removed, before, after
            ))
    return blocks


def _insertion_gaps(block, path, distances):
    first = block[2]
    last = block[3]
    internal = block[5]
    choices = []
    for gap in range(len(path) - 1):
        u = path[gap]
        v = path[gap + 1]
        cost = internal + min(
            distances[u][first] + distances[last][v],
            distances[u][last] + distances[first][v]
        ) - distances[u][v]
        choices.append((cost, gap))
    choices.sort()
    # Removing at most three customers invalidates at most four old gaps.
    return choices[:5]


def _insertion_after_removal(block, removed, choices, distances):
    u = removed[7]
    v = removed[8]
    first = block[2]
    last = block[3]
    best = block[5] + min(
        distances[u][first] + distances[last][v],
        distances[u][last] + distances[first][v]
    ) - distances[u][v]

    for cost, gap in choices:
        if gap < removed[0] or gap > removed[1]:
            best = min(best, cost)
            break
    return best


def _pair_gain(blocks_a, blocks_b, path_a, path_b,
               load_a, load_b, capacity, distances):
    into_b = []
    for block in blocks_a:
        into_b.append(_insertion_gaps(block, path_b, distances))
    into_a = []
    for block in blocks_b:
        into_a.append(_insertion_gaps(block, path_a, distances))

    slack_a = capacity - load_a
    slack_b = capacity - load_b
    best = 0.0

    for k, block in enumerate(blocks_a):
        if block[4] <= slack_b:
            best = max(best, block[6] - into_b[k][0][0])
    for k, block in enumerate(blocks_b):
        if block[4] <= slack_a:
            best = max(best, block[6] - into_a[k][0][0])

    for ia, a in enumerate(blocks_a):
        for ib, b in enumerate(blocks_b):
            difference = b[4] - a[4]
            if difference > slack_a or -difference > slack_b:
                continue
            cost_b = _insertion_after_removal(
                a, b, into_b[ia], distances
            )
            cost_a = _insertion_after_removal(
                b, a, into_a[ib], distances
            )
            best = max(best, a[6] + b[6] - cost_a - cost_b)
    return best


def _record(group, routes, sizes, costs, exposures,
            contact, transfer, blocked, seen, pool):
    ids = tuple(sorted(group))
    customers = []
    count = 0
    exposure = 0.0
    for rid in ids:
        customers.extend(routes[rid])
        count += sizes[rid]
        exposure += exposures[rid]
    union = tuple(sorted(customers))
    if union in blocked or union in seen:
        return
    seen.add(union)

    captured = 0.0
    saturated = 0.0
    for a, rid in enumerate(ids):
        strongest = 0.0
        for other in ids:
            if other != rid:
                strongest = max(strongest, transfer[rid][other])
        saturated += strongest
        for other in ids[a + 1:]:
            captured += contact[rid][other]

    if len(ids) == 1:
        captured = costs[ids[0]]
        tier = 2
    elif len(ids) < 5:
        tier = 1
    else:
        tier = 0

    work = pow(25.0 + count, 0.8)
    exposure_discount = sqrt(1.0 + 0.10 * exposure / max(1, count))
    divisor = work * exposure_discount
    pool.append((
        tier, 0.5 * saturated / divisor,
        captured / divisor, count, ids
    ))


def choose_delegations(problem, state, history, limits):
    routes = state.routes
    nr = len(routes)
    customer_cap = limits.max_customers
    route_cap = min(9, limits.max_routes)
    output_cap = limits.max_delegations
    if nr == 0 or customer_cap < 1 or route_cap < 1 or output_cap < 1:
        return []

    sizes = [len(route) for route in routes]
    eligible = [r for r in range(nr) if sizes[r] <= customer_cap]
    if not eligible:
        return []

    blocked = set()
    for entry in history:
        blocked.add(tuple(entry.selected_customer_ids))

    coordinates = problem.coordinates
    demands = problem.demands
    depot = problem.depot_id
    capacity = problem.capacity
    nn = len(coordinates)
    distances = [[0.0] * nn for _ in range(nn)]
    nodes = [depot]
    for route in routes:
        nodes.extend(route)

    for index, u in enumerate(nodes):
        x, y = coordinates[u]
        for j in range(index):
            v = nodes[j]
            dx = x - coordinates[v][0]
            dy = y - coordinates[v][1]
            distance = sqrt(dx * dx + dy * dy)
            distances[u][v] = distance
            distances[v][u] = distance

    paths = []
    loads = []
    costs = []
    exposures = []
    centers = []
    local_scale = [0.0] * nn
    total_internal = 0.0
    internal_edges = 0

    for route in routes:
        path = (depot,) + route + (depot,)
        paths.append(path)
        loads.append(sum(demands[u] for u in route))
        costs.append(sum(
            distances[path[k]][path[k + 1]]
            for k in range(len(path) - 1)
        ))
        exposures.append(sum(state.node_selection_counts[u] for u in route))
        centers.append((
            sum(coordinates[u][0] for u in route) / len(route),
            sum(coordinates[u][1] for u in route) / len(route)
        ))
        for k, u in enumerate(route):
            length = 0.0
            degree = 0
            if k > 0:
                length += distances[u][route[k - 1]]
                degree += 1
            if k + 1 < len(route):
                length += distances[u][route[k + 1]]
                degree += 1
                total_internal += distances[u][route[k + 1]]
                internal_edges += 1
            local_scale[u] = length / max(1, degree)

    base_scale = total_internal / max(1, internal_edges)
    if base_scale <= 1e-12:
        base_scale = sum(distances[depot][u] for u in nodes)
        base_scale /= max(1.0, len(nodes) * sqrt(len(nodes)))
    base_scale = max(base_scale, 1e-9)

    contact = [[0.0] * nr for _ in range(nr)]
    transfer = [[0.0] * nr for _ in range(nr)]
    center_distance = [[0.0] * nr for _ in range(nr)]
    for i in eligible:
        for j in eligible:
            dx = centers[i][0] - centers[j][0]
            dy = centers[i][1] - centers[j][1]
            center_distance[i][j] = dx * dx + dy * dy

    if route_cap >= 2:
        for i in eligible:
            for u in routes[i]:
                row = distances[u]
                nearest = []
                for j in eligible:
                    if j == i:
                        continue
                    distance = min(row[v] for v in routes[j])
                    nearest.append((distance, j))
                nearest.sort()
                scale = 0.5 * (base_scale + max(local_scale[u], 0.25 * base_scale))
                for rank, item in enumerate(nearest[:3]):
                    distance, j = item
                    weight = scale * scale / (scale + distance)
                    weight /= rank + 1
                    contact[i][j] += weight
                    contact[j][i] += weight

    neighbors = [[] for _ in range(nr)]
    pairs = set()
    contact_seed_scores = []
    contact_seed_seen = set()

    if route_cap >= 2:
        for i in eligible:
            ranked = []
            for j in eligible:
                if i == j or sizes[i] + sizes[j] > customer_cap:
                    continue
                affinity = contact[i][j] / sqrt(sizes[i] * sizes[j])
                ranked.append((-affinity, center_distance[i][j], j))
            ranked.sort()
            neighbors[i] = [item[2] for item in ranked[:8]]
            for j in neighbors[i]:
                pairs.add((min(i, j), max(i, j)))
            if ranked:
                j = ranked[0][2]
                pair = (min(i, j), max(i, j))
                if pair not in contact_seed_seen:
                    contact_seed_seen.add(pair)
                    contact_seed_scores.append((
                        ranked[0][0], ranked[0][1], pair
                    ))

    blocks = [[] for _ in range(nr)]
    for i in eligible:
        if neighbors[i]:
            blocks[i] = _blocks(routes[i], demands, distances, depot)

    transfer_seed_scores = []
    for i, j in sorted(pairs):
        if not blocks[i]:
            blocks[i] = _blocks(routes[i], demands, distances, depot)
        if not blocks[j]:
            blocks[j] = _blocks(routes[j], demands, distances, depot)
        gain = _pair_gain(
            blocks[i], blocks[j], paths[i], paths[j],
            loads[i], loads[j], capacity, distances
        )
        transfer[i][j] = gain
        transfer[j][i] = gain
        if gain > 1e-9:
            count = sizes[i] + sizes[j]
            exposure = (exposures[i] + exposures[j]) / count
            priority = gain / sqrt(25.0 + count)
            priority /= sqrt(1.0 + 0.10 * exposure)
            transfer_seed_scores.append((-priority, i, j))

    transfer_seed_scores.sort()
    contact_seed_scores.sort()
    seeds = []
    seed_seen = set()
    seed_limit = min(96, max(24, 2 * len(eligible)))

    for score, i, j in transfer_seed_scores[:seed_limit]:
        pair = (i, j)
        if pair not in seed_seen:
            seed_seen.add(pair)
            seeds.append(pair)
    for score, distance, pair in contact_seed_scores[:64]:
        if pair not in seed_seen:
            seed_seen.add(pair)
            seeds.append(pair)

    seen = set()
    pool = []
    for seed in seeds:
        group = list(seed)
        members = set(seed)
        count = sum(sizes[r] for r in seed)
        attachment = [0.0] * nr
        for j in eligible:
            attachment[j] = sum(contact[j][r] for r in seed)

        _record(
            group, routes, sizes, costs, exposures,
            contact, transfer, blocked, seen, pool
        )
        while len(group) < route_cap:
            best = -1
            best_key = None
            for j in eligible:
                if j in members or count + sizes[j] > customer_cap:
                    continue
                distance = min(center_distance[j][r] for r in group)
                key = (
                    attachment[j] / sqrt(sizes[j]),
                    -distance, -j
                )
                if best == -1 or key > best_key:
                    best = j
                    best_key = key
            if best == -1:
                break

            group.append(best)
            members.add(best)
            count += sizes[best]
            for j in eligible:
                attachment[j] += contact[j][best]

            if len(group) in (3, 5, 7, 9):
                _record(
                    group, routes, sizes, costs, exposures,
                    contact, transfer, blocked, seen, pool
                )

        _record(
            group, routes, sizes, costs, exposures,
            contact, transfer, blocked, seen, pool
        )

    for i in eligible:
        _record(
            [i], routes, sizes, costs, exposures,
            contact, transfer, blocked, seen, pool
        )

    if not pool:
        return []

    chosen = [False] * len(pool)
    overlaps = [0.0] * len(pool)
    result = []
    for position in range(min(output_cap, len(pool))):
        tier = 3
        for k, candidate in enumerate(pool):
            if not chosen[k]:
                tier = min(tier, candidate[0])

        lane = position % 2
        if lane == 0:
            has_transfer = False
            for k, candidate in enumerate(pool):
                if not chosen[k] and candidate[0] == tier and candidate[1] > 0.0:
                    has_transfer = True
                    break
            if not has_transfer:
                lane = 1

        best = -1
        best_key = None
        for k, candidate in enumerate(pool):
            if chosen[k] or candidate[0] != tier:
                continue
            diversity = 1.0 - 0.65 * overlaps[k] * overlaps[k] * overlaps[k]
            key = (
                candidate[1 + lane] * diversity,
                candidate[2 - lane] * diversity,
                -candidate[3]
            )
            if best == -1 or key > best_key:
                best = k
                best_key = key

        if best == -1:
            break
        chosen[best] = True
        selected = pool[best]
        result.append(list(selected[4]))
        selected_routes = set(selected[4])

        for k, candidate in enumerate(pool):
            if chosen[k]:
                continue
            common = sum(
                sizes[r] for r in candidate[4] if r in selected_routes
            )
            if common:
                similarity = common / sqrt(candidate[3] * selected[3])
                overlaps[k] = max(overlaps[k], similarity)

    return result

from math import sqrt


def sample_blocks(route, demands, distance):
    blocks = []
    n = len(route)
    for length in range(1, min(3, n) + 1):
        available = n - length + 1
        count = available if length == 1 else min(4, available)
        for t in range(count):
            start = t if length == 1 else (
                t * (available - 1) // max(1, count - 1)
            )
            stop = start + length
            first = route[start]
            last = route[stop - 1]
            left = route[start - 1] if start else 0
            right = route[stop] if stop < n else 0
            demand = 0.0
            internal = 0.0
            for p in range(start, stop):
                demand += demands[route[p]]
                if p > start:
                    internal += distance[route[p - 1]][route[p]]
            saving = (
                distance[left][first]
                + internal
                + distance[last][right]
                - distance[left][right]
            )
            blocks.append((
                start, stop, first, last, demand, internal,
                saving, left, right
            ))
    return blocks


def insertion_shortlist(block, route, distance):
    first = block[2]
    last = block[3]
    internal = block[5]
    costs = []
    left = 0
    for gap in range(len(route) + 1):
        right = route[gap] if gap < len(route) else 0
        forward = distance[left][first] + distance[last][right]
        backward = distance[left][last] + distance[first][right]
        cost = min(forward, backward) + internal - distance[left][right]
        costs.append((cost, gap))
        left = right
    costs.sort()
    # Removing at most three consecutive customers deletes at most four
    # original gaps. Five cheapest gaps therefore suffice for exact repair.
    return costs[:5]


def insertion_after_removal(block, removed, shortlist, distance):
    best = 1.0e100
    for cost, gap in shortlist:
        if gap < removed[0] or gap > removed[1]:
            best = cost
            break
    left = removed[7]
    right = removed[8]
    first = block[2]
    last = block[3]
    forward = distance[left][first] + distance[last][right]
    backward = distance[left][last] + distance[first][right]
    bridge = (
        min(forward, backward) + block[5] - distance[left][right]
    )
    return min(best, bridge)


def pair_transfer_gain(
    route_a, route_b, blocks_a, blocks_b, load_a, load_b,
    capacity, distance
):
    into_b = [
        insertion_shortlist(block, route_b, distance)
        for block in blocks_a
    ]
    into_a = [
        insertion_shortlist(block, route_a, distance)
        for block in blocks_b
    ]
    best = 0.0

    for p, block in enumerate(blocks_a):
        if load_b + block[4] <= capacity:
            gain = block[6] - into_b[p][0][0]
            if gain > best:
                best = gain
    for q, block in enumerate(blocks_b):
        if load_a + block[4] <= capacity:
            gain = block[6] - into_a[q][0][0]
            if gain > best:
                best = gain

    for p, block_a in enumerate(blocks_a):
        demand_a = block_a[4]
        for q, block_b in enumerate(blocks_b):
            demand_b = block_b[4]
            if load_a - demand_a + demand_b > capacity:
                continue
            if load_b - demand_b + demand_a > capacity:
                continue
            removed_cost = block_a[6] + block_b[6]
            # Euclidean insertion costs are nonnegative.
            if removed_cost <= best:
                continue
            insert_a = insertion_after_removal(
                block_a, block_b, into_b[p], distance
            )
            insert_b = insertion_after_removal(
                block_b, block_a, into_a[q], distance
            )
            gain = removed_cost - insert_a - insert_b
            if gain > best:
                best = gain
    return best


def save_patch(
    group, routes, sizes, contact, degree, transfer, exposure,
    blocked, seen, candidates, max_routes, max_customers
):
    if not group or len(group) > max_routes:
        return
    ordered = tuple(sorted(group))
    count = sum(sizes[r] for r in ordered)
    if count > max_customers:
        return
    customers = []
    for r in ordered:
        customers.extend(routes[r])
    union = tuple(sorted(customers))
    if union in blocked or union in seen:
        return
    seen.add(union)

    captured = 0.0
    saturated = 0.0
    total_degree = 0.0
    total_exposure = 0.0
    for p, r in enumerate(ordered):
        strongest = 0.0
        for s in ordered:
            if transfer[r][s] > strongest:
                strongest = transfer[r][s]
        saturated += strongest
        total_degree += degree[r]
        total_exposure += exposure[r]
        for s in ordered[p + 1:]:
            captured += contact[r][s]

    saturated *= 0.5
    closure = 2.0 * captured / max(1.0e-12, total_degree)
    denominator = pow(max(1, count), 0.65)
    denominator *= 1.0 + 0.08 * total_exposure / max(1, count)

    # Broad patches are the main portfolio. Small, almost closed patches
    # can compete; other small prefixes remain available as fallbacks.
    tier = 0
    if len(ordered) < min(5, max_routes):
        if closure < 0.85 or saturated <= 0.0:
            tier = 1
    candidates.append((
        ordered, count, saturated / denominator,
        captured / denominator, tier
    ))


def choose_delegations(problem, state, history, limits):
    routes = state.routes
    route_count = len(routes)
    max_routes = limits.max_routes
    max_customers = limits.max_customers
    max_delegations = limits.max_delegations
    if (
        route_count == 0 or max_routes < 1 or max_customers < 1
        or max_delegations < 1 or state.current_cost <= 0.0
    ):
        return []

    blocked = set()
    for entry in history:
        blocked.add(tuple(sorted(entry.selected_customer_ids)))

    sizes = [len(route) for route in routes]
    eligible = [
        r for r in range(route_count)
        if sizes[r] <= max_customers
    ]
    if not eligible:
        return []

    if max_routes == 1 or len(eligible) == 1:
        result = []
        for r in eligible:
            if tuple(sorted(routes[r])) not in blocked:
                result.append([r])
                if len(result) >= max_delegations:
                    break
        return result

    coordinates = problem.coordinates
    demands = problem.demands
    capacity = problem.capacity
    node_count = len(coordinates)
    distance = [[0.0] * node_count for _ in range(node_count)]
    for u in range(node_count):
        x, y = coordinates[u]
        for v in range(u):
            dx = x - coordinates[v][0]
            dy = y - coordinates[v][1]
            value = sqrt(dx * dx + dy * dy)
            distance[u][v] = value
            distance[v][u] = value

    loads = [0.0] * route_count
    exposure = [0.0] * route_count
    centers = [(0.0, 0.0)] * route_count
    route_costs = [0.0] * route_count
    total_internal = 0.0
    internal_edges = 0
    for r, route in enumerate(routes):
        sx = 0.0
        sy = 0.0
        previous = 0
        cost = 0.0
        for p, u in enumerate(route):
            loads[r] += demands[u]
            exposure[r] += state.node_selection_counts[u]
            sx += coordinates[u][0]
            sy += coordinates[u][1]
            cost += distance[previous][u]
            if p:
                total_internal += distance[previous][u]
                internal_edges += 1
            previous = u
        cost += distance[previous][0]
        route_costs[r] = cost
        centers[r] = (sx / sizes[r], sy / sizes[r])

    if total_internal > 0.0:
        scale = total_internal / max(1, internal_edges)
    else:
        scale = state.current_cost / max(1, sum(sizes))
    scale = max(scale, 1.0e-9)

    # Each customer votes for three nearby foreign routes. A vote has
    # distance units and is not a capacity feasibility test.
    contact = [[0.0] * route_count for _ in range(route_count)]
    for r in eligible:
        route = routes[r]
        for p, u in enumerate(route):
            row = distance[u]
            local = 0.0
            edges = 0
            if p:
                local += row[route[p - 1]]
                edges += 1
            if p + 1 < len(route):
                local += row[route[p + 1]]
                edges += 1
            local = local / edges if edges else scale
            local = max(local, 0.25 * scale)
            nearby = []
            for s in eligible:
                if s == r:
                    continue
                nearest = min(row[v] for v in routes[s])
                nearby.append((nearest, s))
            nearby.sort()
            for gap, s in nearby[:3]:
                contact[r][s] += local / (1.0 + gap / scale)

    for r in range(route_count):
        for s in range(r):
            value = contact[r][s] + contact[s][r]
            contact[r][s] = value
            contact[s][r] = value
    degree = [sum(row) for row in contact]

    center_distance = [
        [0.0] * route_count for _ in range(route_count)
    ]
    for r in eligible:
        for s in eligible:
            if s < r:
                dx = centers[r][0] - centers[s][0]
                dy = centers[r][1] - centers[s][1]
                value = sqrt(dx * dx + dy * dy)
                center_distance[r][s] = value
                center_distance[s][r] = value

    # Only a bounded union of contact-neighbor pairs receives move search.
    pair_keys = set()
    contact_seeds = set()
    for r in eligible:
        neighbors = []
        for s in eligible:
            if s != r and sizes[r] + sizes[s] <= max_customers:
                neighbors.append((
                    -contact[r][s], center_distance[r][s], s
                ))
        neighbors.sort()
        for position, item in enumerate(neighbors[:8]):
            s = item[2]
            pair = (min(r, s), max(r, s))
            pair_keys.add(pair)
            if position == 0:
                contact_seeds.add(pair)

    blocks = [[] for _ in range(route_count)]
    for r in eligible:
        blocks[r] = sample_blocks(routes[r], demands, distance)

    transfer = [[0.0] * route_count for _ in range(route_count)]
    ranked_transfers = []
    ranked_contacts = []
    for r, s in sorted(pair_keys):
        gain = pair_transfer_gain(
            routes[r], routes[s], blocks[r], blocks[s],
            loads[r], loads[s], capacity, distance
        )
        transfer[r][s] = gain
        transfer[s][r] = gain
        if gain > 0.0:
            ranked_transfers.append((-gain, r, s))
        ranked_contacts.append((-contact[r][s], r, s))
    ranked_transfers.sort()
    ranked_contacts.sort()

    seeds = []
    seed_seen = set()
    seed_limit = min(96, 2 * len(eligible))
    for negative_gain, r, s in ranked_transfers[:seed_limit]:
        pair = (r, s)
        seeds.append(pair)
        seed_seen.add(pair)
    for pair in sorted(contact_seeds):
        if pair not in seed_seen:
            seeds.append(pair)
            seed_seen.add(pair)
    for negative_contact, r, s in ranked_contacts[:len(eligible)]:
        pair = (r, s)
        if pair not in seed_seen:
            seeds.append(pair)
            seed_seen.add(pair)

    candidates = []
    seen = set()
    growth_limit = min(9, max_routes, len(eligible))
    for seed in seeds:
        group = list(seed)
        members = set(group)
        customers = sum(sizes[r] for r in group)
        attachment = [0.0] * route_count
        for s in eligible:
            attachment[s] = sum(contact[r][s] for r in group)

        while True:
            if len(group) in (2, 3, 5, 7, 9):
                save_patch(
                    group, routes, sizes, contact, degree, transfer,
                    exposure, blocked, seen, candidates,
                    max_routes, max_customers
                )
            if len(group) >= growth_limit:
                break

            best_route = -1
            best_key = None
            for s in eligible:
                if s in members or customers + sizes[s] > max_customers:
                    continue
                proximity = min(center_distance[r][s] for r in group)
                key = (
                    attachment[s] / sqrt(sizes[s]),
                    -proximity,
                    -s
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_route = s
            if best_route < 0:
                break
            group.append(best_route)
            members.add(best_route)
            customers += sizes[best_route]
            for s in eligible:
                attachment[s] += contact[best_route][s]

        # Retain the terminal feasible prefix when a cap interrupts growth.
        save_patch(
            group, routes, sizes, contact, degree, transfer,
            exposure, blocked, seen, candidates,
            max_routes, max_customers
        )

    result = []
    used = set()
    overlap = [0.0] * len(candidates)
    while len(result) < max_delegations and len(used) < len(candidates):
        tier = min(
            candidates[p][4] for p in range(len(candidates))
            if p not in used
        )
        lane = len(result) % 2
        best_index = -1
        best_value = -1.0
        for attempt in range(2):
            column = 2 if lane == 0 else 3
            for p, candidate in enumerate(candidates):
                if p in used or candidate[4] != tier:
                    continue
                value = candidate[column] / (1.0 + overlap[p])
                if value > best_value:
                    best_value = value
                    best_index = p
            if best_value > 0.0:
                break
            lane = 1 - lane
            best_value = -1.0
            best_index = -1

        if best_index < 0:
            break
        chosen = candidates[best_index]
        used.add(best_index)
        result.append(list(chosen[0]))
        chosen_routes = set(chosen[0])
        for p, candidate in enumerate(candidates):
            if p in used:
                continue
            shared = sum(
                sizes[r] for r in candidate[0] if r in chosen_routes
            )
            fraction = shared / max(1, min(chosen[1], candidate[1]))
            if fraction > overlap[p]:
                overlap[p] = fraction

    # Single routes remain legal backups when caps or history leave little
    # joint coverage. Their unions are checked exactly like joint patches.
    if len(result) < max_delegations:
        singletons = []
        for r in eligible:
            union = tuple(sorted(routes[r]))
            if union not in blocked and union not in seen:
                singletons.append((
                    -route_costs[r] / sqrt(sizes[r]), r, union
                ))
        singletons.sort()
        for priority, r, union in singletons:
            result.append([r])
            seen.add(union)
            if len(result) >= max_delegations:
                break
    return result

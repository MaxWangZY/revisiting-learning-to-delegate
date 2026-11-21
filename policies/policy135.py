from math import sqrt


def _placement(block, left, right, distance):
    first = block[4]
    last = block[5]
    forward = distance[left][first] + distance[last][right]
    backward = distance[left][last] + distance[first][right]
    return min(forward, backward) + block[7] - distance[left][right]


def _make_blocks(route, demands, distance, depot):
    n = len(route)
    blocks = []
    short_count = 0
    for width in range(1, min(3, n) + 1):
        for start in range(n - width + 1):
            end = start + width
            left = depot if start == 0 else route[start - 1]
            right = depot if end == n else route[end]
            first = route[start]
            last = route[end - 1]
            load = 0.0
            inside = 0.0
            for p in range(start, end):
                load += demands[route[p]]
                if p + 1 < end:
                    inside += distance[route[p]][route[p + 1]]
            removed = (
                distance[left][first] + inside
                + distance[last][right] - distance[left][right]
            )
            block = (
                start, end, left, right, first, last,
                load, inside, removed, 0.0
            )
            best_insertion = _placement(block, left, right, distance)
            for gap in range(n + 1):
                if start <= gap <= end:
                    continue
                a = depot if gap == 0 else route[gap - 1]
                b = depot if gap == n else route[gap]
                value = _placement(block, a, b, distance)
                if value < best_insertion:
                    best_insertion = value
            standalone = max(0.0, removed - best_insertion)
            blocks.append((
                start, end, left, right, first, last,
                load, inside, removed, standalone
            ))
        if width <= 2:
            short_count = len(blocks)
    return blocks, short_count


def _extend_insertion_table(blocks, start, target, distance, depot, table):
    n = len(target)
    for p in range(start, len(blocks)):
        block = blocks[p]
        choices = []
        for gap in range(n + 1):
            left = depot if gap == 0 else target[gap - 1]
            right = depot if gap == n else target[gap]
            choices.append((_placement(block, left, right, distance), gap))
        choices.sort()
        table.append(choices[:5])


def _after_removal(table, outgoing, incoming, distance):
    best = _placement(incoming, outgoing[2], outgoing[3], distance)
    for value, gap in table:
        if gap < outgoing[0] or gap > outgoing[1]:
            if value < best:
                best = value
            break
    return best


def _pair_gain(
    blocks_a, blocks_b, table_ab, table_ba,
    load_a, load_b, capacity, distance, old_a, old_b, best
):
    na = len(table_ab)
    nb = len(table_ba)

    for p in range(old_a, na):
        block = blocks_a[p]
        if load_b + block[6] <= capacity:
            gain = block[8] - block[9] - table_ab[p][0][0]
            if gain > best:
                best = gain
    for q in range(old_b, nb):
        block = blocks_b[q]
        if load_a + block[6] <= capacity:
            gain = block[8] - block[9] - table_ba[q][0][0]
            if gain > best:
                best = gain

    for p in range(na):
        a = blocks_a[p]
        credit_a = a[8] - a[9]
        for q in range(nb):
            if p < old_a and q < old_b:
                continue
            b = blocks_b[q]
            change = b[6] - a[6]
            if load_a + change > capacity or load_b - change > capacity:
                continue
            bound = credit_a + b[8] - b[9]
            if bound <= best:
                continue
            cost_ab = _after_removal(table_ab[p], b, a, distance)
            if bound - cost_ab <= best:
                continue
            cost_ba = _after_removal(table_ba[q], a, b, distance)
            gain = bound - cost_ab - cost_ba
            if gain > best:
                best = gain
    return best


def _save_patch(
    group, routes, sizes, exposure, contact, transfer,
    contact_total, seen, candidates, customer_cap, small_target
):
    ids = tuple(sorted(group))
    count = sum(sizes[r] for r in ids)
    if count > customer_cap:
        return

    customers = []
    for r in ids:
        customers.extend(routes[r])
    key = tuple(sorted(customers))
    if key in seen:
        return
    seen.add(key)

    internal = 0.0
    saturated = 0.0
    incident = 0.0
    selected_before = 0.0
    for p in range(len(ids)):
        i = ids[p]
        incident += contact_total[i]
        selected_before += exposure[i]
        strongest = 0.0
        for q in range(len(ids)):
            j = ids[q]
            if i != j and transfer[i][j] > strongest:
                strongest = transfer[i][j]
            if q > p:
                internal += contact[i][j]
        saturated += strongest

    closure = 2.0 * internal / max(incident, 2.0 * internal, 1e-12)
    work = pow(20.0 + count, 0.85) * (1.0 + (count / 140.0) ** 2)
    work *= 1.0 + 0.06 * selected_before / max(1, count)
    small_factor = min(1.0, len(ids) / max(1, small_target)) ** 2
    transfer_score = small_factor * 0.5 * saturated / work
    contact_score = small_factor * internal * (0.5 + 0.5 * closure) / work
    candidates.append((transfer_score, contact_score, count, ids))


def _single_backups(
    eligible, routes, sizes, route_cost, distance, depot, blocked, count
):
    ranked = []
    for r in eligible:
        if sizes[r] < 3:
            continue
        key = tuple(sorted(routes[r]))
        if key in blocked:
            continue
        radius = max(distance[depot][u] for u in routes[r])
        headroom = max(0.0, route_cost[r] - 2.0 * radius)
        if headroom > 0.0:
            ranked.append((-headroom / (20.0 + sizes[r]), r))
    ranked.sort()
    return [[r] for value, r in ranked[:count]]


def choose_delegations(problem, state, history, limits):
    routes = state.routes
    route_count = len(routes)
    if (
        route_count == 0 or limits.max_routes < 1
        or limits.max_customers < 1 or limits.max_delegations < 1
    ):
        return []

    sizes = [len(route) for route in routes]
    eligible = [
        r for r in range(route_count)
        if sizes[r] <= limits.max_customers
    ]
    if not eligible:
        return []

    blocked = set()
    for entry in history:
        blocked.add(tuple(sorted(entry.selected_customer_ids)))

    coordinates = problem.coordinates
    depot = problem.depot_id
    node_count = len(coordinates)
    active = [depot]
    for route in routes:
        active.extend(route)
    distance = [[0.0] * node_count for p in range(node_count)]
    for p in range(len(active)):
        u = active[p]
        x, y = coordinates[u]
        for q in range(p + 1, len(active)):
            v = active[q]
            dx = x - coordinates[v][0]
            dy = y - coordinates[v][1]
            value = sqrt(dx * dx + dy * dy)
            distance[u][v] = value
            distance[v][u] = value

    loads = [0.0] * route_count
    exposure = [0.0] * route_count
    route_cost = [0.0] * route_count
    local_scale = [0.0] * node_count
    interior_length = 0.0
    interior_edges = 0
    for r in range(route_count):
        route = routes[r]
        previous = depot
        for p in range(len(route)):
            u = route[p]
            following = depot if p + 1 == len(route) else route[p + 1]
            route_cost[r] += distance[previous][u]
            loads[r] += problem.demands[u]
            exposure[r] += state.node_selection_counts[u]
            local_scale[u] = 0.5 * (
                distance[previous][u] + distance[u][following]
            )
            if p + 1 < len(route):
                interior_length += distance[u][following]
                interior_edges += 1
            previous = u
        route_cost[r] += distance[previous][depot]

    if limits.max_routes == 1 or len(eligible) == 1:
        return _single_backups(
            eligible, routes, sizes, route_cost, distance,
            depot, blocked, limits.max_delegations
        )

    if interior_edges:
        scale = interior_length / interior_edges
    else:
        scale = sum(route_cost) / max(1, 2 * (len(active) - 1))
    scale = max(scale, 1e-9)

    contact = [[0.0] * route_count for r in range(route_count)]
    nearest = [[1e100] * route_count for r in range(route_count)]
    for i in eligible:
        nearest[i][i] = 0.0
        for u in routes[i]:
            foreign = []
            row = distance[u]
            for j in eligible:
                if i == j:
                    continue
                closest = min(row[v] for v in routes[j])
                foreign.append((closest, j))
                if closest < nearest[i][j]:
                    nearest[i][j] = closest
            foreign.sort()
            length = max(0.5 * scale, min(3.0 * scale, local_scale[u]))
            for rank in range(min(3, len(foreign))):
                gap, j = foreign[rank]
                weight = length * length / (length + gap)
                weight /= rank + 1
                contact[i][j] += weight
                contact[j][i] += weight

    contact_total = [sum(row) for row in contact]
    pair_set = set()
    contact_seed_set = set()
    for i in eligible:
        neighbors = []
        for j in eligible:
            if i != j and sizes[i] + sizes[j] <= limits.max_customers:
                neighbors.append((-contact[i][j], nearest[i][j], j))
        neighbors.sort()
        for value, gap, j in neighbors[:6]:
            pair_set.add((min(i, j), max(i, j)))
        if neighbors:
            j = neighbors[0][2]
            contact_seed_set.add((min(i, j), max(i, j)))

    if not pair_set:
        return _single_backups(
            eligible, routes, sizes, route_cost, distance,
            depot, blocked, limits.max_delegations
        )

    blocks = [[] for r in range(route_count)]
    short_counts = [0] * route_count
    for r in eligible:
        row, short_count = _make_blocks(
            routes[r], problem.demands, distance, depot
        )
        blocks[r] = row
        short_counts[r] = short_count

    transfer = [[0.0] * route_count for r in range(route_count)]
    transfer_seeds = []
    epsilon = 1e-10 * max(1.0, scale)

    for i, j in sorted(pair_set):
        ni = short_counts[i]
        nj = short_counts[j]
        table_ij = []
        table_ji = []
        _extend_insertion_table(
            blocks[i][:ni], 0, routes[j], distance, depot, table_ij
        )
        _extend_insertion_table(
            blocks[j][:nj], 0, routes[i], distance, depot, table_ji
        )
        gain = _pair_gain(
            blocks[i], blocks[j], table_ij, table_ji,
            loads[i], loads[j], problem.capacity, distance, 0, 0, 0.0
        )

        # A triple is searched only when shorter cooperative moves fail.
        if gain <= epsilon:
            _extend_insertion_table(
                blocks[i], ni, routes[j], distance, depot, table_ij
            )
            _extend_insertion_table(
                blocks[j], nj, routes[i], distance, depot, table_ji
            )
            gain = _pair_gain(
                blocks[i], blocks[j], table_ij, table_ji,
                loads[i], loads[j], problem.capacity,
                distance, ni, nj, max(0.0, gain)
            )

        if gain > epsilon:
            transfer[i][j] = gain
            transfer[j][i] = gain
            visits = (exposure[i] + exposure[j]) / (sizes[i] + sizes[j])
            priority = gain / (1.0 + 0.06 * visits)
            transfer_seeds.append((-priority, -contact[i][j], i, j))

    transfer_seeds.sort()
    seed_limit = min(64, max(24, len(eligible)))
    seeds = []
    seed_seen = set()
    for value, tie, i, j in transfer_seeds[:seed_limit]:
        pair = (i, j)
        seed_seen.add(pair)
        seeds.append(pair)

    contact_seeds = []
    for i, j in sorted(contact_seed_set):
        visits = (exposure[i] + exposure[j]) / (sizes[i] + sizes[j])
        value = contact[i][j] / (1.0 + 0.06 * visits)
        contact_seeds.append((-value, nearest[i][j], i, j))
    contact_seeds.sort()
    for value, gap, i, j in contact_seeds[:64]:
        pair = (i, j)
        if pair not in seed_seen:
            seed_seen.add(pair)
            seeds.append(pair)

    maximum_width = min(9, limits.max_routes, len(eligible))
    small_target = min(5, maximum_width)
    seen = set(blocked)
    candidates = []
    for seed in seeds:
        group = list(seed)
        membership = set(group)
        count = sum(sizes[r] for r in group)
        attachment = [0.0] * route_count
        for j in eligible:
            attachment[j] = sum(contact[i][j] for i in group)

        while True:
            width = len(group)
            if width in (2, 3, 5, 7, 9) or width == maximum_width:
                _save_patch(
                    group, routes, sizes, exposure, contact, transfer,
                    contact_total, seen, candidates,
                    limits.max_customers, small_target
                )
            if width >= maximum_width:
                break

            best_route = -1
            best_key = (-1.0, -1e100, -route_count)
            for j in eligible:
                if j in membership or count + sizes[j] > limits.max_customers:
                    continue
                affinity = attachment[j] / sqrt(sizes[j])
                separation = min(nearest[i][j] for i in group)
                key = (affinity, -separation, -j)
                if key > best_key:
                    best_key = key
                    best_route = j
            if best_route < 0:
                _save_patch(
                    group, routes, sizes, exposure, contact, transfer,
                    contact_total, seen, candidates,
                    limits.max_customers, small_target
                )
                break

            group.append(best_route)
            membership.add(best_route)
            count += sizes[best_route]
            for j in eligible:
                attachment[j] += contact[best_route][j]

    if not candidates:
        return _single_backups(
            eligible, routes, sizes, route_cost, distance,
            depot, blocked, limits.max_delegations
        )

    selected = [False] * len(candidates)
    overlap = [0.0] * len(candidates)
    route_uses = [0] * route_count
    result = []

    for position in range(min(limits.max_delegations, len(candidates))):
        lane = position % 2
        best_index = -1
        best_key = (-1.0, -1.0, -1e100, -len(candidates))
        for p in range(len(candidates)):
            if selected[p]:
                continue
            candidate = candidates[p]
            repeated = sum(
                sizes[r] * route_uses[r] for r in candidate[3]
            ) / candidate[2]
            discount = (
                1.0 + 1.25 * overlap[p] * overlap[p] + 0.06 * repeated
            )
            key = (
                candidate[lane] / discount,
                candidate[1 - lane] / discount,
                -candidate[2],
                -p
            )
            if key > best_key:
                best_key = key
                best_index = p
        if best_index < 0:
            break

        selected[best_index] = True
        chosen = candidates[best_index]
        chosen_routes = set(chosen[3])
        result.append(list(chosen[3]))
        for r in chosen[3]:
            route_uses[r] += 1

        for p in range(len(candidates)):
            if selected[p]:
                continue
            candidate = candidates[p]
            common = sum(
                sizes[r] for r in candidate[3] if r in chosen_routes
            )
            union_size = chosen[2] + candidate[2] - common
            similarity = common / max(1, union_size)
            if similarity > overlap[p]:
                overlap[p] = similarity

    return result

import numpy as np
import matplotlib.pyplot as plt
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection

def edge_geometry(G, u, v):
    data = G.get_edge_data(u, v)
    if data is None: return None
    if G.is_multigraph():
        key, attrs = min(list(data.items()), key=lambda item: item[1].get("travel_time_s", float("inf")))
    else:
        attrs = data
    geometry = attrs.get("geometry")
    if geometry is not None: return np.asarray(geometry.coords)
    return np.asarray([[G.nodes[u]["x"], G.nodes[u]["y"]], [G.nodes[v]["x"], G.nodes[v]["y"]]])

def plot_map_view(G, result, instance, is_shortest_path=False):
    fig, ax = ox.plot_graph(
        G, show=False, close=False, node_size=0,
        edge_color="#eef0f2", edge_linewidth=0.35, bgcolor="white", figsize=(10, 5)
    )
    ax.set_axis_off()
    
    depot = instance.depot
    customer_nodes = [c.node for c in instance.customers]
    route_colors = ["#D90429", "#0077B6", "#2A9D8F", "#F4A261", "#7209B7"]
    legend_handles = []

    for vehicle_idx, route in enumerate(result["routes"]):
        if len(route) <= 2 and route[0] == route[-1]: continue
        vehicle_segments = []
        color = route_colors[vehicle_idx % len(route_colors)]

        for a, b in zip(route[:-1], route[1:]):
            path = result["paths"].get((a, b))
            if not path or len(path) < 2: continue
            for u, v in zip(path[:-1], path[1:]):
                coords = edge_geometry(G, u, v)
                if coords is not None and len(coords) >= 2:
                    vehicle_segments.append(coords)

        if vehicle_segments:
            lc = LineCollection(vehicle_segments, colors=[color], linewidths=1.2, alpha=0.9, zorder=4, capstyle="round")
            ax.add_collection(lc)
            label = "Path Trajectory" if is_shortest_path else f"Vehicle {vehicle_idx + 1}"
            legend_handles.append(Line2D([0], [0], color=color, lw=2, label=label))

    c_x = [G.nodes[n]["x"] for n in customer_nodes if n in G.nodes]
    c_y = [G.nodes[n]["y"] for n in customer_nodes if n in G.nodes]
    cust_label = "Destination(s)" if is_shortest_path else "Customer"
    ax.scatter(c_x, c_y, s=40, marker="o", facecolor="white", edgecolor="#111827", linewidth=1.0, zorder=7)

    if depot in G.nodes:
        dx, dy = G.nodes[depot]["x"], G.nodes[depot]["y"]
        depot_label = "Origin Node" if is_shortest_path else "Depot Base"
        ax.scatter([dx], [dy], s=180, marker="*", facecolor="#D90429", edgecolor="white", linewidth=1.0, zorder=8)

    all_x = [data['x'] for n, data in G.nodes(data=True)]
    all_y = [data['y'] for n, data in G.nodes(data=True)]
    if all_x and all_y:
        pad_x, pad_y = (max(all_x) - min(all_x)) * 0.02, (max(all_y) - min(all_y)) * 0.02
        ax.set_xlim(min(all_x) - pad_x, max(all_x) + pad_x)
        ax.set_ylim(min(all_y) - pad_y, max(all_y) + pad_y)

    legend_handles.extend([
        Line2D([0], [0], marker="*", color="none", markerfacecolor="#D90429", markeredgecolor="white", markersize=12, label=depot_label),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor="#111827", markersize=6, label=cust_label),
    ])

    ax.legend(handles=legend_handles, loc="best", frameon=True, framealpha=0.9, edgecolor="#e5e7eb", fontsize=9, ncol=min(4, len(legend_handles)))
    fig.tight_layout(pad=0)
    return fig

def plot_graph_view(G, result, instance, is_shortest_path=False):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_facecolor("white")
    ax.axis("off")

    depot = instance.depot
    customer_nodes = [c.node for c in instance.customers]
    nodes_to_plot = [depot] + customer_nodes
    route_colors = ["#D90429", "#0077B6", "#2A9D8F", "#F4A261", "#7209B7"]
    legend_handles = []

    for vehicle_idx, route in enumerate(result["routes"]):
        if len(route) <= 2 and route[0] == route[-1]: continue
        color = route_colors[vehicle_idx % len(route_colors)]
        route_coords = [(G.nodes[n]['x'], G.nodes[n]['y']) for n in route if n in G.nodes]

        if route_coords:
            xs, ys = zip(*route_coords)
            ax.plot(xs, ys, color=color, linewidth=2.0, alpha=0.85, zorder=4, linestyle="--")
            for i in range(len(xs)-1):
                ax.annotate("", xy=(xs[i+1], ys[i+1]), xytext=(xs[i], ys[i]), arrowprops=dict(arrowstyle="->", color=color, lw=1.5, alpha=0.7))
            label = "Path Topology" if is_shortest_path else f"Vehicle {vehicle_idx + 1}"
            legend_handles.append(Line2D([0], [0], color=color, lw=2, linestyle="--", label=label))

    for c in instance.customers:
        if c.node in G.nodes:
            x, y = G.nodes[c.node]['x'], G.nodes[c.node]['y']
            ax.scatter(x, y, s=350, marker="o", facecolor="white", edgecolor="#111827", linewidth=2.0, zorder=7)
            if not is_shortest_path:
                ax.text(x, y, str(int(c.demand)), fontsize=9, ha='center', va='center', fontweight='bold', color="#111827", zorder=8)

    if depot in G.nodes:
        dx, dy = G.nodes[depot]["x"], G.nodes[depot]["y"]
        depot_label = "Origin Node" if is_shortest_path else "Depot Node"
        ax.scatter([dx], [dy], s=500, marker="*", facecolor="#D90429", edgecolor="white", linewidth=1.5, zorder=8)

    x = [G.nodes[n]['x'] for n in nodes_to_plot if n in G.nodes]
    y = [G.nodes[n]['y'] for n in nodes_to_plot if n in G.nodes]
    if x and y:
        pad_x, pad_y = (max(x) - min(x)) * 0.1, (max(y) - min(y)) * 0.1
        if pad_x == 0: pad_x = 0.01
        if pad_y == 0: pad_y = 0.01
        ax.set_xlim(min(x) - pad_x, max(x) + pad_x)
        ax.set_ylim(min(y) - pad_y, max(y) + pad_y)

    cust_label = "Destination Node" if is_shortest_path else "Customer (Value = Demand)"
    legend_handles.extend([
        Line2D([0], [0], marker="*", color="none", markerfacecolor="#D90429", markeredgecolor="white", markersize=14, label=depot_label),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor="#111827", markersize=10, label=cust_label),
    ])

    ax.legend(handles=legend_handles, loc="best", frameon=True, framealpha=0.9, edgecolor="#e5e7eb", fontsize=9, ncol=min(3, len(legend_handles)))
    fig.tight_layout(pad=0)
    return fig
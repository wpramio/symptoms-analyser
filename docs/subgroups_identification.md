To help the clinician identify separate subgroups/cliques and isolated patients in the network, we have implemented three complementary visual features in the graph page:

1. Connected Components Detection & Node Clustering
We added a Breadth-First Search (BFS) algorithm to detect connected components of the social cohesion interaction graph on the fly.
Instead of laying out patients purely by numerical order, the graph layout now clusters nodes by their connected component.
This means that all patients in the same subgroup are placed in adjacent positions along the circle's arc, while isolated patients are placed together at the end. Since interaction lines only span within their respective subgroup arcs, the separation between the subgroups is immediately visible and free of crossing lines.
2. Color-Coded Borders & Tooltip Badges
Each patient node receives a thick, distinctively colored border representing their detected subgroup (e.g., Subgrupo A in Purple, Subgrupo B in Rose/Red, etc.). Isolated patients receive a standard neutral white border.
When hovering over any patient node, the tooltip now dynamically displays their subgroup classification (e.g., SUBGRUPO A or PACIENTE ISOLADO) directly under the patient's ID.
3. Interactive "Cohesive Subgroups" Legend
We added a dynamic, interactive legend panel below the standard interaction type legends.
It displays each identified subgroup name, its color, and its members (e.g. Subgrupo A (Paciente1, Paciente2...)).
Hover Interaction: Hovering over a subgroup in this legend highlights only that subgroup's patients and the internal interaction paths connecting them, while fading out the rest of the graph. Hovering over the isolated members item highlights only the isolated patients.


How we can help the clinician identify subgroups even when bridging interactions exist:
In real-world therapy groups, subgroups often have one or two "bridges" (weak ties) between them rather than being 100% disconnected. To prevent a single bridging interaction from completely merging distinct subgroups in the clinician's view, we can introduce modularity/community detection or bridge edge detection:

Option A: K-Core / Edge-Cut Filtering (Filtering out Weak Bridges)
We can ignore edges that do not meet a certain threshold or structure (e.g. only group nodes into a subgroup if they share at least $k$ mutual links, or if we ignore "weak bridges").

Option B: Simple Path/Bridge Highlighting (Visualizing Bridging Links)
We can identify "bridges" (edges whose removal increases the number of connected components) and render them with a dashed line or a distinct style. This shows the clinician: "These two groups are connected, but only through this specific interaction between Paciente3 and Paciente10."

Option C: Local Community Detection (e.g. Clique Percolation or Degree Clustering)
We can group nodes based on their clustering coefficient or mutual neighbors rather than pure connectivity. For example, if two nodes are in the same subgroup, they should share a higher density of local connections.
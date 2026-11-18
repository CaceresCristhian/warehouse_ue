This repository contains a synthetic dataset for the order picking problem in manual, rectangular warehouses.
It is designed to support replication, benchmarking, and comparison of routing and waiting heuristics, as well as general algorithms for order picking.

Each instance represents one working day, i.e., one shift of 8 hours.

Repository Structure

Top-level folders:

    Data_input/ – Static input data (warehouse layouts and storage assignments)
    Orders/ – Order streams (instances) for different experimental settings
    Results/ – Example/benchmark solutions for selected instances (for validation)

Within Data_input/ and Orders/, data is split into two experimental designs:

    OFAT/ – One-Factor-at-a-Time design
    LHS/ – Latin Hypercube Sampling design

Simplified structure:
.
├── Data_input/
│   ├── OFAT/
│   │   ├── Layout/
│   │   ├── Storage_assignment/
│   │   └── ...
│   └── LHS/
│       ├── Layout/
│       ├── Storage_assignment/
│       └── ...
├── Orders/
│   ├── OFAT/
│   │   ├── Standard_case/
│   │   ├── article_distribution/
│   │   ├── due_date/
│   │   ├── Layout/
│   │   ├── Nr_orders/
│   │   ├── num_articles_in_order/
│   │   ├── Stochasticity/
│   │   └── Storage_Policy/
│   └── LHS/
│       └── <100 parameter sets>/
└── Results/
    ├── OFAT/
    └── LHS/

    Orders/OFAT/Standard_case/ contains the baseline setting.
    Each other folder under Orders/OFAT/ changes exactly one factor relative to the standard case.
    Orders/LHS/ contains 100 parameter sets (Latin Hypercube Sampling), each with 100 replications.

Warehouse Layouts
Geometric and Logical Structure

The warehouse is modeled as a rectangular layout with:

    Parallel picking aisles
    One cross aisle at the bottom and one at the top
    A depot at coordinate (0, 0) (in abstract length units)

Layouts are represented as NetworkX graphs stored as pickle files (*.pkl) in Data_input/.../Layout/.

Nodes:

    Picking locations:  
        Node IDs: (i, j) with i in {1, ..., n_aisles}, j in {1, ..., n_pick_locations}  
        Attribute: type = "pick_node"  
        Position attribute: pos = (i, j); positions are consistent with the layout  
        These nodes are used as potential storage/picking positions and are referenced by the storage assignment

    Change-aisle nodes (cross aisles):  
        Bottom: (i, 0) for i in {1, ..., n_aisles}  
        Top: (i, n_pick_locations + 1) for i in {1, ..., n_aisles}  
        Attribute: type = "change_aisle_node"  
        Position attribute: pos = (i, 0) (bottom) or pos = (i, n_pick_locations + 1) (top)

    Start node (depot origin, external to the grid):  
        Default: start_location = (0, 0)  
        Attribute: type = "start_node"  
        Position attribute: pos = (0, 0)  
        Connected to a node in the first aisle via an edge with length dist_start.

    End node:  
        Default: end_location = (1, -1)  
        Attribute: type = "end_node"  
        Position attribute: pos = (1, -1)  
        Connected to a node in the last aisle via an edge with length dist_end.

Edges:

    Vertical edges: between (aisle, location) and (aisle, location + 1) within an aisle  

    Bottom connections: between (aisle, 0) and (aisle, 1)  

    Top connections: between (aisle, n_pick_locations) and (aisle, n_pick_locations + 1)  

    Horizontal edges (cross aisles):  
        Bottom: between (aisle, 0) and (aisle + 1, 0)  
        Top: between (aisle, n_pick_locations + 1) and (aisle + 1, n_pick_locations + 1)  

    Depot connections:  
        Between start_location and start_connection_point (e.g. (1, 0))
        Between end_location and end_connection_point (e.g. (n_aisles, 0))

Units:

    All distances are expressed in abstract length units
    All times (arrival times, due dates) are expressed in seconds

An example of how a layout graph is loaded (simplified):

    Load a pickle file (graph = pickle.load(file))
    Extract:
        pick_nodes as all nodes with data["type"] == "pick_node"
        start_node and end_node based on node attributes (type containing "start_node" / "end_node")
        Distance matrix and tour matrix (if needed) based on edge weights

Storage Assignments

Storage assignments are stored as JSON files in Data_input/.../Storage_assignment/.

Format:
{
    "<article_id_1>": [x1, y1],
    "<article_id_2>": [x2, y2],
    ...
}

    Each key is an article ID
    Each value is a 2D coordinate (x, y) that corresponds to a pick node in the layout
    There is a 1:1 relationship between locations and articles (no scattered storage)
    These coordinates are consistent with the node IDs in the layout graph

In meta, each instance specifies its storage assignment via the key:

    meta["storage_assignment"] = relative path to the corresponding JSON file.

Storage policies (see section “OFAT: Storage_Policy”) define how these assignments are generated (e.g. placing A-items closer to the depot, etc.), but once generated, the storage assignment is simply a dictionary mapping articles to coordinates.

Order Instances (JSON)

Each file in Orders/ is a JSON file representing one replication (= one shift/day) for a given parameter setting.

Top-level structure:

    meta: metadata and configuration of the instance
    orders: list of orders for this instance

meta structure

meta is a dictionary with the following keys:

    layout
    Relative path to the layout file in Data_input/.../Layout/.
    Format example: "../../Data_input/OFAT/Layout/layout_8x16.pkl"
    The file contains a NetworkX graph (see section “Warehouse Layouts”).

    storage_assignment
    Relative path to the storage assignment file in Data_input/.../Storage_assignment/.
    The file is a JSON dictionary mapping article_id to (x, y) coordinates.

    num_instances
    Number of replications in this parameter folder (typically 100).

    exp_num_orders
    Expected number of orders per shift for this parameter setting.

    max_simulation_time
    Length of the simulated shift in seconds (8 hours).

    arrival_config
    Configuration of the order arrival process. This may include:
        The type of inter-arrival time distribution (e.g., "exponential" for exponential interarrival times).
        For wave-based arrivals: number of waves (here: 5) and a stochasticity parameter in [0, 1], where:
            0 = Poisson-like arrivals, no waves
            1 = strong waves, high volatility

    num_articles_in_order_config
    Distribution of the number of articles (order lines) per order. Depending on the setting, this can be:
        A fixed value, e.g. fixed_value_1 (every order contains exactly one article).
        A discrete distribution with fields like:
            population: list of possible order sizes (number of articles per order).
            weights: corresponding probabilities.

    due_date_config
    Configuration of due dates. Examples:
        All orders are due at the end of the shift ("shift_end").
        Fixed times relative to arrival, e.g. 600 or 1800 seconds after arrival.
        A mixed distribution (e.g. part of orders due at shift end, part 1800 s, part 600 s after arrival).

    article_config
    Configuration of item occurrence probabilities per order. Examples:
        Uniform random distribution over all articles.
        ABC-type distributions with given fractions and weights (see section “OFAT: article_distribution”).

    storage_policy
    The storage policy applied when creating the storage assignment, e.g.:
        "random": uniform random assignment.
        "A-to-X" or "A-to-Y": A-items stored at lowest X- or Y-coordinates.
        "A-Closest-to-Depot": A-items stored closest to the depot.

orders structure

orders is a list of order dictionaries, each containing:

    order_id
    Unique identifier of the order (per instance).

    items
    A dictionary of the form {article_id: quantity_to_pick} specifying which articles and how many units must be picked for this order.

    arrival_time
    Arrival time of the order in seconds, measured from the start of the shift.

    due_date
    Due date of the order in seconds, measured from the start of the shift.
    The relationship between arrival time and due date is defined by due_date_config.

OFAT Design (One-Factor-at-a-Time)

The OFAT design is organized in subfolders under Orders/OFAT/.
Each folder modifies exactly one factor relative to the Standard_case/.

Each OFAT subfolder contains:

    A set of factor levels (e.g. multiple due date settings, layout variants, etc.).
    For each factor level: 100 JSON instances (replications), each representing one shift.

Standard_case/

    Contains the baseline parameter setting for all factors.
    Serves as the reference instance set for comparison.
    Includes 100 JSON instances with identical configuration (up to randomness).

article_distribution/

    Varies the distribution of article demand within orders.

    Implements an ABC-distributed demand with:
        Class fractions: [0.2, 0.3, 0.5] (A, B, C)
        Demand weights: [0.8, 0.15, 0.05]

    Interpretation:
        20% of articles (A-items) account for 80% of the demand probability.
        30% (B-items) account for 15%.
        50% (C-items) account for 5%.

This affects meta["article_config"] and is typically required for meaningful storage policies that distinguish between A/B/C items.

due_date/

    Contains three different due date configurations:
         All orders due 600 seconds after arrival.
         All orders due 1800 seconds after arrival.
         Mixed distribution:
            80% of orders: due at shift end.
            15% of orders: due 1800 seconds after arrival.
            5% of orders: due 600 seconds after arrival.

This allows modeling different urgency levels and a share of urgent orders (e.g. for production supply or spare parts).

Layout/

    Contains multiple warehouse layouts. Examples include:
        A standard layout (used in Standard_case).
        8 x 16: same number of pick nodes as the standard case, but more, shorter aisles (different ratio between number of aisles and positions per aisle).
        32 x 4: same number of pick nodes, but fewer, longer aisles (increased length-to-width ratio).
        32 x 16: same aspect ratio as the standard layout, but larger in both dimensions (aisles twice as long and twice as many).

Each layout is stored as a NetworkX graph (*.pkl) and referenced via meta["layout"].

Nr_orders/

    Varies the expected number of orders per shift:
        15 different levels from 500 to 2000 orders in steps of 100 (500, 600, ..., 2000).

This mainly affects meta["exp_num_orders"] and the arrival process configuration.

num_articles_in_order/

    Varies the distribution of the number of articles (order lines) per order.

Examples:

    fixed_value_1: every order contains exactly one article.
    Other variants define:
        population: a list of possible order sizes.
        weights: probabilities for each size.

This information is stored in meta["num_articles_in_order_config"].

Stochasticity/

    Modifies the volatility of the order arrival process.

    Arrivals do not necessarily follow a Poisson process. Instead, they can be wave-shaped.

    arrival_config includes:
        waves: number of waves (here: typically 5).
        stochasticity: wave amplitude parameter in [0, 1]:
            0: arrivals are Poisson distributed (no waves).
            1: arrivals show strong waves (high volatility).

    Three volatility levels are provided:
        0.0, 0.5, and 1.0.

Storage_Policy/

    Contains three storage policy variants for the mapping of articles to storage positions. These are meaningful in combination with ABC-distributed article frequencies.

Policies:

    random (in the Standard Case)
    Uniform random assignment of articles to available storage locations.

    A-to-X
    A-items (most frequent) are placed at the lowest X-coordinates in the warehouse.

    A-to-Y
    A-items are placed at the lowest Y-coordinates.

    A-Closest-to-Depot
    A-items are placed at locations that are closest to the depot (start node), typically with minimal graph distance to (0, 0).

In all cases, the result is a 1:1 mapping from articles to locations, stored in the corresponding JSON file in Data_input/.../Storage_assignment/ and referenced via meta["storage_assignment"].

LHS Design (Latin Hypercube Sampling)

The LHS design jointly varies multiple parameters instead of changing one factor at a time.

Location: Orders/LHS/

    Contains 100 different parameter sets (Latin Hypercube samples).
    For each parameter set: 100 replications (instances).

Parameters varied in the LHS:

    Layout length
    Layout width
    Stochasticity of the arrival process
    Number of orders per shift
    Due date configuration

Fixed choices in LHS:

    Article occurrence probabilities follow an ABC-distribution.
    storage_policy is always "A-Closest-to-Depot".

The JSON structure of each LHS instance is identical to the OFAT instances (meta + orders).
This design allows studying interactions between layout, order volume, arrival volatility, and due dates under a realistic, performance-oriented storage policy.

Results

The Results/ folder contains example/benchmark solutions for selected instances, separated into OFAT and LHS.

Typical use cases:

    Validate that parsing of meta, layout, storage_assignment, and orders is correct.
    Compare new algorithms against basic strategies or previously obtained heuristics.

In our results, we show the values for the KPIs mean length per item (average distance to walk to pick one item), mean order completion time (average time from arrival to fulfillment of an order) and tardiness (average lateness of an order).

Benchmarking and Example Strategies

This dataset can be used to test a wide range of order picking strategies. In particular, it has been used to evaluate:

    Basic batching strategies:
        FCFS (First-Come-First-Served) batching

    Routing heuristics:
        Nearest Neighbour
        Return routing
        S-shape routing
        Largest gap Routing

    Waiting policies:
        Waiting for n orders in the batch before starting the tour (with n ranging from 0 up to the batch capacity)

Any other routing, batching, and scheduling approaches can be evaluated in the same way by using the provided layout, storage_assignment, and orders information.

How to Use the Dataset

Typical steps to use and replicate experiments:

     
    Select a scenario  
        Choose either an OFAT folder (e.g. Standard_case, Layout, Stochasticity) or an LHS parameter set.
        Within that folder, select one or more JSON instance files.
     

    Load the warehouse layout  
        Read the file given by meta["layout"] (NetworkX graph in .pkl format).
        Extract:
            Nodes and edges
            Node types (pick_node, change_aisle_node, start_node, end_node)
            Edge weights for distance calculations
     

    Load the storage assignment  
        Read the file given by meta["storage_assignment"] (JSON).
        Use the mapping {article_id: (x, y)} to translate each article in the orders into node coordinates in the layout.
     

    Parse the orders  
        For each element in orders:
            Use arrival_time (seconds from shift start)
            Use due_date (seconds from shift start)
            Use items to know which articles and quantities must be picked
     

    Apply routing, batching, and waiting algorithms
  	Group orders into batches according to your batching policy (e.g. FCFS, waiting for n orders).
        Use the layout graph and distances to construct picker routes (e.g., nearest neighbour, S-shape, etc.).
        Simulate the picking process over the shift given the arrival process and due dates.
     

    Evaluate performance  
        Compute metrics of interest (e.g., total travel distance, tardiness, order completion time).
        Compare your results across scenarios (OFAT factors, LHS parameter sets) and optionally with the example results in Results/.

Reproducibility

    Every instance fully specifies:
        The layout (meta["layout"]),
        The storage assignment (meta["storage_assignment"]),
        The order stream (orders) including arrival times and due dates,
        The key distributional assumptions (arrival_config, num_articles_in_order_config, due_date_config, article_config).

    All necessary input files (Data_input/) are included and consistently referenced by relative paths in the JSON files.

    This allows full replication of experiments and straightforward comparison of new algorithms on the same standardized instance sets.
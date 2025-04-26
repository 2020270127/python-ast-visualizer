import ast
from graphviz import Digraph

# Parse the server.py file into an AST
with open('server.py', 'r', encoding='utf-8') as f:
    code_text = f.read()
tree = ast.parse(code_text)

# Helper to detect if an AST node (or any of its children) uses the Flask 'request' (external input)
def is_external_input(node):
    if node is None:
        return False
    return any(isinstance(n, ast.Name) and n.id == 'request' for n in ast.walk(node))

# Find all yaml.load call nodes and classify them as external or internal
yaml_load_calls = []
class FindYamlLoad(ast.NodeVisitor):
    def __init__(self):
        self.current_func = None  # track enclosing function name
    def visit_FunctionDef(self, node):
        prev = self.current_func
        self.current_func = node.name
        self.generic_visit(node)
        self.current_func = prev
    def visit_ClassDef(self, node):
        self.generic_visit(node)  # just traverse into class body
    def visit_Call(self, node):
        # Check if it's a call to yaml.load
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'load':
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'yaml':
                yaml_load_calls.append((node, self.current_func))
        self.generic_visit(node)

FindYamlLoad().visit(tree)

# Determine external/internal for each yaml.load call
external_calls = set()
internal_calls = set()
for call_node, func_name in yaml_load_calls:
    # If the call’s argument originates from request or the call is in _external_load, mark external
    first_arg = call_node.args[0] if call_node.args else None
    if func_name == '_external_load' or is_external_input(first_arg):
        external_calls.add(id(call_node))
    else:
        internal_calls.add(id(call_node))

# Prepare Graphviz Digraph
dot = Digraph(name="AST", comment="AST of server.py")
dot.attr('graph', bgcolor='white', rankdir='LR')
dot.attr('node', style='filled', fontcolor='black', color='black', fillcolor='white')
dot.attr('edge', fontcolor='black')

node_counter = 0
node_ids = {}  # map ast node id to graph node name

# Recursive function to add nodes and edges to the graph
def add_node(node, parent_id=None, field_name=None):
    global node_counter
    nid = node_ids.get(id(node))
    if nid is None:
        # Assign a new graph node ID
        nid = f"node{node_counter}"
        node_ids[id(node)] = nid
        node_counter += 1
        # Create a label for this AST node
        label_parts = []  
        node_type = type(node).__name__
        # Base label is the AST node type
        # (We will append additional info for certain types below)
        label = node_type

        # Include key information based on node type
        if isinstance(node, ast.FunctionDef):
            label = f"FunctionDef: name={node.name}, args={len(node.args.args)}"
        elif isinstance(node, ast.ClassDef):
            label = f"ClassDef: name={node.name}"
        elif isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
            label = "Import: " + ", ".join(mods)
        elif isinstance(node, ast.ImportFrom):
            mods = [alias.name for alias in node.names]
            label = f"ImportFrom: {node.module}, names=" + ", ".join(mods)
        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                label = f"Assign: {node.targets[0].id} = ..."
            else:
                label = "Assign"
        elif isinstance(node, ast.Return):
            label = "Return"
        elif isinstance(node, ast.Call):
            # Identify the function being called for label
            func = node.func
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    func_name = f"{func.value.id}.{func.attr}"
                elif isinstance(func.value, ast.Attribute) and isinstance(func.value.value, ast.Name):
                    # handle attribute chain (e.g., obj.method.attr)
                    func_name = f"{func.value.value.id}.{func.value.attr}.{func.attr}"
                else:
                    func_name = func.attr
            else:
                func_name = node_type  # fallback to node type if unusual callable
            label = f"Call: {func_name} (args={len(node.args)})"
            # Mark external/internal on yaml.load calls
            if id(node) in external_calls:
                label += " [external]"
                dot.node(nid, label=label, fillcolor="lightcoral")  # red background
            elif id(node) in internal_calls:
                label += " [internal]"
                dot.node(nid, label=label, fillcolor="lightblue")  # blue background
        elif isinstance(node, ast.Attribute):
            label = f"Attribute: .{node.attr}"
        elif isinstance(node, ast.Name):
            ctx = type(node.ctx).__name__  # Load/Store
            label = f"Name: {node.id} ({ctx})"
        elif isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, str):
                # For long strings, truncate in label
                s = val.replace("\n", "\\n")
                if len(s) > 20:
                    s = s[:17] + "..."
                label = f"Constant: \"{s}\""
            else:
                label = f"Constant: {val}"
        elif isinstance(node, ast.arg):
            label = f"arg: {node.arg}"
        elif isinstance(node, ast.For):
            label = "For"
        elif isinstance(node, ast.If):
            label = "If"
        elif isinstance(node, ast.While):
            label = "While"
        elif isinstance(node, ast.Try):
            label = "Try"
        elif isinstance(node, ast.ExceptHandler):
            label = "ExceptHandler"
        elif isinstance(node, ast.List):
            label = f"List (elts={len(node.elts)})"
        elif isinstance(node, ast.Tuple):
            label = f"Tuple (elts={len(node.elts)})"
        elif isinstance(node, ast.Dict):
            # number of key-value pairs
            count = len(node.keys) if node.keys else 0
            label = f"Dict (pairs={count})"
        elif isinstance(node, ast.Set):
            label = f"Set (elts={len(node.elts)})"
        elif isinstance(node, ast.ListComp):
            label = "ListComp"
        elif isinstance(node, ast.GeneratorExp):
            label = "GeneratorExp"
        elif isinstance(node, ast.comprehension):
            label = "comprehension"
        elif isinstance(node, ast.With):
            label = "With"
        elif isinstance(node, ast.withitem):
            label = "withitem"
        # (Other node types will just use the base type name)

        # Add the node to the graph (if not already added above for call coloring)
        if not (isinstance(node, ast.Call) and (id(node) in external_calls or id(node) in internal_calls)):
            dot.node(nid, label=label)
    else:
        # Node already visited; use existing nid
        nid = node_ids[id(node)]

    # Add an edge from parent to this node (with field name or index if available)
    if parent_id:
        edge_label = ""
        if field_name is not None:
            edge_label = str(field_name)
        dot.edge(parent_id, nid, label=edge_label)

    # Recurse into children fields
    for field, value in ast.iter_fields(node):
        if isinstance(value, ast.AST):
            add_node(value, nid, field)
        elif isinstance(value, list):
            for idx, elem in enumerate(value):
                if isinstance(elem, ast.AST):
                    # Label list edges with index
                    add_node(elem, nid, f"{field}[{idx}]")

# Build the graph starting from the root of the AST
add_node(tree)

# Render the AST graph to file (e.g., PNG image)
dot.format = 'png'
dot.render('server_ast_graph', cleanup=True)
print("AST visualization saved as server_ast_graph.png")

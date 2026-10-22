# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helper for building Geometry Nodes and shader trees from Python.

Swayfield's node groups are written as code ("nodes as code") rather than
shipped as a binary .blend, so they can be reviewed, diffed and tested. The
built groups are saved inside the user's file, so files still render without
the add-on installed.

Typical use::

    b = NodeBuilder(tree)
    pos = b.out("GeometryNodeInputPosition")
    up = b.vmath("NORMALIZE", pos)
    b.link(up, b.group_output.inputs["Vector"])
    b.arrange()

Sockets are addressed by index or by name. Name lookups skip disabled
sockets, so polymorphic nodes (Math, Random Value, Switch, ...) resolve to the
socket that matches their current data type. Always set node properties
(``data_type``, ``operation``, ...) before connecting, which ``node()`` does.
"""

from __future__ import annotations

from collections.abc import Iterable

import bpy

from .. import spec

Socket = bpy.types.NodeSocket


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def add_socket(tree, name: str, socket_type: str, in_out: str = "INPUT", *, parent=None,
               default=None, min_value=None, max_value=None, subtype: str = "NONE",
               description: str = "", hidden: bool = False):
    """Add one interface socket. ``socket_type`` is a spec type (``"FLOAT"``) or a bl_idname."""
    idname = spec.SOCKET_TYPES.get(socket_type, socket_type)
    kwargs = {"in_out": in_out, "socket_type": idname}
    if parent is not None:
        kwargs["parent"] = parent
    sock = tree.interface.new_socket(name, **kwargs)
    if description:
        sock.description = description
    if subtype != "NONE" and hasattr(sock, "subtype"):
        try:
            sock.subtype = subtype
        except TypeError:
            pass  # subtype not available in this Blender version
    if min_value is not None and hasattr(sock, "min_value"):
        sock.min_value = min_value
    if max_value is not None and hasattr(sock, "max_value"):
        sock.max_value = max_value
    if default is not None and hasattr(sock, "default_value"):
        sock.default_value = default
    if hidden and hasattr(sock, "hide_in_modifier"):
        sock.hide_in_modifier = True
    if idname in {"NodeSocketString", "NodeSocketObject", "NodeSocketCollection",
                  "NodeSocketMaterial", "NodeSocketImage", "NodeSocketBool", "NodeSocketInt"} \
            and in_out == "INPUT" and hasattr(sock, "force_non_field"):
        sock.force_non_field = True
    return sock


def add_spec_inputs(tree, keys: Iterable[str] | None = None, *, panels: bool = True) -> None:
    """Add spec inputs to ``tree``, in spec order.

    ``keys=None`` adds every input. With ``panels=True`` inputs are grouped in
    interface panels named after ``spec.Input.panel``.
    """
    wanted = None if keys is None else set(keys)
    if wanted is not None:
        unknown = wanted - spec.BY_KEY.keys()
        if unknown:
            raise KeyError(f"unknown spec keys: {sorted(unknown)}")
    panel_items = {}
    for item in spec.INPUTS:
        if wanted is not None and item.key not in wanted:
            continue
        parent = None
        if panels and item.panel:
            parent = panel_items.get(item.panel)
            if parent is None:
                parent = tree.interface.new_panel(item.panel, default_closed=True)
                panel_items[item.panel] = parent
        add_socket(tree, item.name, item.type, parent=parent, default=item.default,
                   min_value=item.min, max_value=item.max, subtype=item.subtype,
                   description=item.description, hidden=item.hidden)


def clear_tree(tree) -> None:
    tree.nodes.clear()
    tree.interface.clear()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _enabled(socket) -> bool:
    return getattr(socket, "enabled", True) and not getattr(socket, "is_unavailable", False)


def find_socket(sockets, key):
    """Resolve ``key`` (index or name) to a socket, preferring enabled sockets."""
    if isinstance(key, int):
        return sockets[key]
    for s in sockets:
        if s.name == key and _enabled(s):
            return s
    for s in sockets:
        if s.identifier == key:
            return s
    raise KeyError(f"no socket {key!r} in {[s.name for s in sockets if _enabled(s)]}")


def first_output(node) -> Socket:
    for s in node.outputs:
        if _enabled(s):
            return s
    raise KeyError(f"{node.bl_idname} has no enabled output")


class NodeBuilder:
    """Creates nodes, sets values and links sockets in one node tree."""

    def __init__(self, tree, *, clear_nodes: bool = True):
        self.tree = tree
        if clear_nodes:
            tree.nodes.clear()
        self._group_input = None
        self._group_output = None

    # -- group input / output ------------------------------------------------

    @property
    def group_input(self):
        if self._group_input is None:
            self._group_input = self.tree.nodes.new("NodeGroupInput")
        return self._group_input

    @property
    def group_output(self):
        if self._group_output is None:
            node = self.tree.nodes.new("NodeGroupOutput")
            node.is_active_output = True
            self._group_output = node
        return self._group_output

    def inp(self, key: str) -> Socket:
        """Group input socket by spec key or socket name."""
        item = spec.BY_KEY.get(key)
        return find_socket(self.group_input.outputs, item.name if item else key)

    def output(self, name: str, value) -> None:
        """Connect ``value`` to the group output called ``name``."""
        self.set(find_socket(self.group_output.inputs, name), value)

    # -- nodes ---------------------------------------------------------------

    def node(self, idname: str, inputs: dict | None = None, *, label: str = "", name: str = "", **props):
        """Create a node, set its properties, then its inputs (values or sockets)."""
        node = self.tree.nodes.new(idname)
        for attr, value in props.items():
            setattr(node, attr, value)
        if label:
            node.label = label
        if name:
            node.name = name
        for key, value in (inputs or {}).items():
            if value is None:
                continue
            self.set(find_socket(node.inputs, key), value)
        return node

    def out(self, idname: str, inputs: dict | None = None, output=None, **props) -> Socket:
        """Create a node and return one output (the first enabled one by default)."""
        node = self.node(idname, inputs, **props)
        return first_output(node) if output is None else find_socket(node.outputs, output)

    def group(self, node_tree, inputs: dict | None = None, *, forward: bool = True, label: str = ""):
        """Add a group node. With ``forward=True`` any group input whose name
        matches an input of this tree's group input is linked automatically."""
        node = self.tree.nodes.new(self._group_node_idname())
        node.node_tree = node_tree
        if label:
            node.label = label
        explicit = set((inputs or {}).keys())
        if forward:
            available = {s.name for s in self.group_input.outputs if _enabled(s)}
            for sock in node.inputs:
                if sock.name in explicit or sock.name not in available:
                    continue
                self.link(find_socket(self.group_input.outputs, sock.name), sock)
        for key, value in (inputs or {}).items():
            if value is not None:
                self.set(find_socket(node.inputs, key), value)
        return node

    def _group_node_idname(self) -> str:
        return {
            "GeometryNodeTree": "GeometryNodeGroup",
            "ShaderNodeTree": "ShaderNodeGroup",
        }[self.tree.bl_idname]

    # -- values and links ----------------------------------------------------

    def link(self, from_socket: Socket, to_socket: Socket):
        return self.tree.links.new(from_socket, to_socket)

    def set(self, socket: Socket, value) -> None:
        """Link if ``value`` is a socket (or node: first output), else set the default."""
        if isinstance(value, bpy.types.Node):
            value = first_output(value)
        if isinstance(value, bpy.types.NodeSocket):
            self.link(value, socket)
        else:
            socket.default_value = value

    # -- shorthands ------------------------------------------------------------

    def math(self, operation: str, a, b=None, c=None, *, clamp: bool = False) -> Socket:
        inputs = {0: a}
        if b is not None:
            inputs[1] = b
        if c is not None:
            inputs[2] = c
        return self.out("ShaderNodeMath", inputs, operation=operation, use_clamp=clamp)

    def vmath(self, operation: str, a, b=None, c=None, *, scale=None) -> Socket:
        inputs = {0: a}
        if b is not None:
            inputs[1] = b
        if c is not None:
            inputs[2] = c
        if scale is not None:
            inputs["Scale"] = scale
        node = self.node("ShaderNodeVectorMath", inputs, operation=operation)
        # DOT_PRODUCT, LENGTH and DISTANCE produce a float on "Value".
        return first_output(node)

    def map_range(self, value, from_min=0.0, from_max=1.0, to_min=0.0, to_max=1.0, *,
                  interpolation: str = "LINEAR", clamp: bool = True) -> Socket:
        node = self.node("ShaderNodeMapRange", {"Value": value, "From Min": from_min, "From Max": from_max,
                                                "To Min": to_min, "To Max": to_max},
                         interpolation_type=interpolation, clamp=clamp, data_type="FLOAT")
        return find_socket(node.outputs, "Result")

    def mix(self, factor, a, b, *, data_type: str = "FLOAT", clamp: bool = True) -> Socket:
        node = self.node("ShaderNodeMix", data_type=data_type, clamp_factor=clamp)
        self.set(find_socket(node.inputs, "Factor"), factor)
        self.set(find_socket(node.inputs, "A"), a)
        self.set(find_socket(node.inputs, "B"), b)
        return find_socket(node.outputs, "Result")

    def compare(self, operation: str, a, b, *, data_type: str = "FLOAT") -> Socket:
        return self.out("FunctionNodeCompare", {"A": a, "B": b}, operation=operation, data_type=data_type)

    def boolean(self, operation: str, a, b=None) -> Socket:
        inputs = {0: a}
        if b is not None:
            inputs[1] = b
        return self.out("FunctionNodeBooleanMath", inputs, operation=operation)

    def switch(self, input_type: str, condition, false, true) -> Socket:
        return self.out("GeometryNodeSwitch", {"Switch": condition, "False": false, "True": true},
                        input_type=input_type)

    def combine_xyz(self, x=0.0, y=0.0, z=0.0) -> Socket:
        return self.out("ShaderNodeCombineXYZ", {"X": x, "Y": y, "Z": z})

    def separate_xyz(self, vector):
        node = self.node("ShaderNodeSeparateXYZ", {"Vector": vector})
        return node.outputs["X"], node.outputs["Y"], node.outputs["Z"]

    def named_attribute(self, name, data_type: str = "FLOAT"):
        """Return ``(attribute, exists)`` sockets of a Named Attribute node."""
        node = self.node("GeometryNodeInputNamedAttribute", {"Name": name}, data_type=data_type)
        return find_socket(node.outputs, "Attribute"), find_socket(node.outputs, "Exists")

    def store(self, geometry, name: str, value, *, data_type: str = "FLOAT", domain: str = "POINT",
              selection=None) -> Socket:
        node = self.node("GeometryNodeStoreNamedAttribute", {"Geometry": geometry, "Name": name},
                         data_type=data_type, domain=domain)
        self.set(find_socket(node.inputs, "Value"), value)
        if selection is not None:
            self.set(find_socket(node.inputs, "Selection"), selection)
        return find_socket(node.outputs, "Geometry")

    def random_float(self, id_=None, seed=0, min_value=0.0, max_value=1.0) -> Socket:
        node = self.node("FunctionNodeRandomValue", data_type="FLOAT")
        self.set(find_socket(node.inputs, "Min"), min_value)
        self.set(find_socket(node.inputs, "Max"), max_value)
        if id_ is not None:
            self.set(find_socket(node.inputs, "ID"), id_)
        self.set(find_socket(node.inputs, "Seed"), seed)
        return find_socket(node.outputs, "Value")

    def value(self, v: float, label: str = "") -> Socket:
        node = self.node("ShaderNodeValue", label=label)
        node.outputs[0].default_value = v
        return node.outputs[0]

    # -- layout ----------------------------------------------------------------

    def arrange(self, x_step: float = 260.0, y_step: float = 190.0) -> None:
        """Lay nodes out left to right by dependency depth, so trees stay readable."""
        nodes = list(self.tree.nodes)
        incoming = {n.name: set() for n in nodes}
        for link in self.tree.links:
            incoming[link.to_node.name].add(link.from_node.name)
        depth: dict[str, int] = {}

        def visit(name: str, stack: frozenset = frozenset()) -> int:
            if name in depth:
                return depth[name]
            if name in stack:
                return 0
            d = 0
            for parent in incoming[name]:
                d = max(d, visit(parent, stack | {name}) + 1)
            depth[name] = d
            return d

        for n in nodes:
            visit(n.name)
        if self._group_output is not None:
            depth[self._group_output.name] = max(depth.values(), default=0) + 1
        columns: dict[int, list] = {}
        for n in nodes:
            columns.setdefault(depth[n.name], []).append(n)
        for col, members in columns.items():
            for row, n in enumerate(members):
                n.location = (col * x_step, -row * y_step)


def ensure_group(name: str, tree_type: str = "GeometryNodeTree"):
    """Return the node group ``name``, creating an empty one if missing."""
    tree = bpy.data.node_groups.get(name)
    if tree is None or tree.bl_idname != tree_type:
        tree = bpy.data.node_groups.new(name, tree_type)
    return tree

"""
BuildPart

name: build_part.py
by:   Gumyr
date: July 12th 2022

desc:
    This python module is a library used to build 3D parts.

TODO:
- add TwistExtrude, ProjectText
- add centered to wedge

license:

    Copyright 2022 Gumyr

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

"""
import inspect
from math import radians, tan
from tkinter import CENTER
from typing import Union
from cadquery import (
    Edge,
    Face,
    Wire,
    Vector,
    Location,
    Vertex,
    Compound,
    Solid,
    Plane,
)
from cadquery.occ_impl.shapes import VectorLike
from build123d.build_common import *
from OCP.gp import gp_Pln, gp_Lin


class BuildPart(Builder):
    """BuildPart

    Create 3D parts (objects with the property of volume) from sketches or 3D objects.

    Args:
        workplane (Plane, optional): initial plane to work on. Defaults to Plane.named("XY").
        mode (Mode, optional): combination mode. Defaults to Mode.ADD.

    """

    @property
    def _obj(self):
        return self.part

    @property
    def pending_edges_as_wire(self) -> Wire:
        """Return a wire representation of the pending edges"""
        return Wire.assembleEdges(self.pending_edges)

    def __init__(
        self,
        workplane: PlaneLike = Plane.named("XY"),
        mode: Mode = Mode.ADD,
    ):
        self.part: Compound = None
        initial_plane = (
            workplane if isinstance(workplane, Plane) else Plane.named(workplane)
        )
        self.initial_plane = initial_plane
        # self.pending_faces: dict[int : list[Face]] = {0: []}
        # self.pending_edges: dict[int : list[Edge]] = {0: []}
        self.pending_faces: list[Face] = []
        self.pending_face_planes: list[Plane] = []
        self.pending_edges: list[Edge] = []
        self.last_faces = []
        self.last_solids = []
        super().__init__(mode, initial_plane)

    def vertices(self, select: Select = Select.ALL) -> ShapeList[Vertex]:
        """Return Vertices from Part

        Return either all or the vertices created during the last operation.

        Args:
            select (Select, optional): Vertex selector. Defaults to Select.ALL.

        Returns:
            VertexList[Vertex]: Vertices extracted
        """
        vertex_list = []
        if select == Select.ALL:
            for edge in self.part.Edges():
                vertex_list.extend(edge.Vertices())
        elif select == Select.LAST:
            vertex_list = self.last_vertices
        return ShapeList(set(vertex_list))

    def edges(self, select: Select = Select.ALL) -> ShapeList[Edge]:
        """Return Edges from Part

        Return either all or the edges created during the last operation.

        Args:
            select (Select, optional): Edge selector. Defaults to Select.ALL.

        Returns:
            ShapeList[Edge]: Edges extracted
        """
        if select == Select.ALL:
            edge_list = self.part.Edges()
        elif select == Select.LAST:
            edge_list = self.last_edges
        return ShapeList(edge_list)

    def faces(self, select: Select = Select.ALL) -> ShapeList[Face]:
        """Return Faces from Part

        Return either all or the faces created during the last operation.

        Args:
            select (Select, optional): Face selector. Defaults to Select.ALL.

        Returns:
            ShapeList[Face]: Faces extracted
        """
        if select == Select.ALL:
            face_list = self.part.Faces()
        elif select == Select.LAST:
            face_list = self.last_faces
        return ShapeList(face_list)

    def solids(self, select: Select = Select.ALL) -> ShapeList[Solid]:
        """Return Solids from Part

        Return either all or the solids created during the last operation.

        Args:
            select (Select, optional): Solid selector. Defaults to Select.ALL.

        Returns:
            ShapeList[Solid]: Solids extracted
        """
        if select == Select.ALL:
            solid_list = self.part.Solids()
        elif select == Select.LAST:
            solid_list = self.last_solids
        return ShapeList(solid_list)

    def _add_to_pending(self, *objects: Union[Edge, Face]):
        """Add objects to BuildPart pending lists

        Args:
            objects (Union[Edge, Face]): sequence of objects to add
        """
        for obj in objects:
            for loc in LocationList._get_context().locations:
                localized_obj = obj.moved(loc)
                if isinstance(obj, Face):
                    logger.debug(
                        f"Adding localized Face to pending_faces at {localized_obj.location()}"
                    )
                    self.pending_faces.append(localized_obj)
                else:
                    logger.debug(
                        f"Adding localized Edge to pending_edges at {localized_obj.location()}"
                    )
                    self.pending_edges.append(localized_obj)

    def _add_to_context(
        self,
        *objects: Union[Edge, Wire, Face, Solid, Compound],
        faces_to_pending: bool = True,
        mode: Mode = Mode.ADD,
    ):
        """Add objects to BuildPart instance

        Core method to interface with BuildPart instance. Input sequence of objects is
        parsed into lists of edges, faces, and solids. Edges and faces are added to pending
        lists. Solids are combined with current part.

        Each operation generates a list of vertices, edges, faces, and solids that have
        changed during this operation. These lists are only guaranteed to be valid up until
        the next operation as subsequent operations can eliminate these objects.

        Args:
            objects (Union[Edge, Wire, Face, Solid, Compound]): sequence of objects to add
            faces_to_pending (bool, optional): add faces to pending_faces. Default to True.
            mode (Mode, optional): combination mode. Defaults to Mode.ADD.

        Raises:
            ValueError: Nothing to subtract from
            ValueError: Nothing to intersect with
            ValueError: Invalid mode
        """
        if mode != Mode.PRIVATE:
            # Sort the provided objects into edges, faces and solids
            new_faces = [obj for obj in objects if isinstance(obj, Face)]
            new_objects = [obj for obj in objects if isinstance(obj, Solid)]
            for compound in filter(lambda o: isinstance(o, Compound), objects):
                new_faces.extend(compound.Faces())
                new_objects.extend(compound.Solids())
            if not faces_to_pending:
                new_objects.extend(new_faces)
                new_faces = []
            new_edges = [obj for obj in objects if isinstance(obj, Edge)]
            for compound in filter(lambda o: isinstance(o, Wire), objects):
                new_edges.extend(compound.Edges())

            pre_vertices = set() if self.part is None else set(self.part.Vertices())
            pre_edges = set() if self.part is None else set(self.part.Edges())
            pre_faces = set() if self.part is None else set(self.part.Faces())
            pre_solids = set() if self.part is None else set(self.part.Solids())

            if new_objects:
                logger.debug(
                    f"Attempting to integrate {len(new_objects)} object(s) into part"
                    f" with Mode={mode}"
                )
                if mode == Mode.ADD:
                    if self.part is None:
                        if len(new_objects) == 1:
                            self.part = new_objects[0]
                        else:
                            self.part = new_objects.pop().fuse(*new_objects)
                    else:
                        self.part = self.part.fuse(*new_objects).clean()
                elif mode == Mode.SUBTRACT:
                    if self.part is None:
                        raise RuntimeError("Nothing to subtract from")
                    self.part = self.part.cut(*new_objects).clean()
                elif mode == Mode.INTERSECT:
                    if self.part is None:
                        raise RuntimeError("Nothing to intersect with")
                    self.part = self.part.intersect(*new_objects).clean()
                elif mode == Mode.REPLACE:
                    self.part = Compound.makeCompound(new_objects).clean()

                logger.info(
                    f"Completed integrating {len(new_objects)} object(s) into part"
                    f" with Mode={mode}"
                )

            post_vertices = set() if self.part is None else set(self.part.Vertices())
            post_edges = set() if self.part is None else set(self.part.Edges())
            post_faces = set() if self.part is None else set(self.part.Faces())
            post_solids = set() if self.part is None else set(self.part.Solids())
            self.last_vertices = list(post_vertices - pre_vertices)
            self.last_edges = list(post_edges - pre_edges)
            self.last_faces = list(post_faces - pre_faces)
            self.last_solids = list(post_solids - pre_solids)

            self._add_to_pending(*new_edges)
            self._add_to_pending(*new_faces)

    @classmethod
    def _get_context(cls) -> "BuildPart":
        """Return the instance of the current builder"""
        logger.info(
            f"Context requested by {type(inspect.currentframe().f_back.f_locals['self']).__name__}"
        )
        return cls._current.get(None)


#
# Operations
#


class CounterBoreHole(Compound):
    """Part Operation: Counter Bore Hole

    Create a counter bore hole in part.

    Args:
        radius (float): hole size
        counter_bore_radius (float): counter bore size
        counter_bore_depth (float): counter bore depth
        depth (float, optional): hole depth - None implies through part. Defaults to None.
        mode (Mode, optional): combination mode. Defaults to Mode.SUBTRACT.
    """

    def __init__(
        self,
        radius: float,
        counter_bore_radius: float,
        counter_bore_depth: float,
        depth: float = None,
        mode: Mode = Mode.SUBTRACT,
    ):
        context: BuildPart = BuildPart._get_context()

        hole_depth = (
            context.part.BoundingBox().DiagonalLength if depth is None else depth
        )
        new_solids = [
            Solid.makeCylinder(radius, hole_depth, (0, 0, 0), (0, 0, -1))
            .fuse(
                Solid.makeCylinder(
                    counter_bore_radius,
                    counter_bore_depth,
                    (0, 0, 0),
                    (0, 0, -1),
                )
            )
            .moved(location)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class CounterSinkHole(Compound):
    """Part Operation: Counter Sink Hole

    Create a counter sink hole in part.

    Args:
        radius (float): hole size
        counter_sink_radius (float): counter sink size
        depth (float, optional): hole depth - None implies through part. Defaults to None.
        counter_sink_angle (float, optional): cone angle. Defaults to 82.
        mode (Mode, optional): combination mode. Defaults to Mode.SUBTRACT.
    """

    def __init__(
        self,
        radius: float,
        counter_sink_radius: float,
        depth: float = None,
        counter_sink_angle: float = 82,  # Common tip angle
        mode: Mode = Mode.SUBTRACT,
    ):
        context: BuildPart = BuildPart._get_context()

        hole_depth = (
            context.part.BoundingBox().DiagonalLength if depth is None else depth
        )
        cone_height = counter_sink_radius / tan(radians(counter_sink_angle / 2.0))
        new_solids = [
            Solid.makeCylinder(radius, hole_depth, (0, 0, 0), (0, 0, -1))
            .fuse(
                Solid.makeCone(
                    counter_sink_radius,
                    0.0,
                    cone_height,
                    (0, 0, 0),
                    (0, 0, -1),
                )
            )
            .moved(location)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Extrude(Compound):
    """Part Operation: Extrude

    Extrude a sketch/face and combine with part.

    Args:
        until (Union[float, Until, Face]): depth of extrude or extrude limit
        both (bool, optional): extrude in both directions. Defaults to False.
        taper (float, optional): taper during extrusion. Defaults to None.
        mode (Mode, optional): combination mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        until: Union[float, Until, Face],
        both: bool = False,
        taper: float = None,
        mode: Mode = Mode.ADD,
    ):
        new_solids: list[Solid] = []
        context: BuildPart = BuildPart._get_context()
        for face in context.pending_faces:
            new_solids.append(
                Solid.extrudeLinear(
                    face,
                    face.normalAt(face.Center()) * until,
                    0,
                )
            )
            if both:
                new_solids.append(
                    Solid.extrudeLinear(
                        face,
                        face.normalAt(face.Center()) * until * -1.0,
                        0,
                    )
                )

        context.pending_faces = []
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Hole(Compound):
    """Part Operation: Hole

    Create a hole in part.

    Args:
        radius (float): hole size
        depth (float, optional): hole depth - None implies through part. Defaults to None.
        mode (Mode, optional): combination mode. Defaults to Mode.SUBTRACT.
    """

    def __init__(
        self,
        radius: float,
        depth: float = None,
        mode: Mode = Mode.SUBTRACT,
    ):
        context: BuildPart = BuildPart._get_context()

        hole_depth = (
            context.part.BoundingBox().DiagonalLength if depth is None else depth
        )
        new_solids = [
            Solid.makeCylinder(radius, hole_depth, (0, 0, 0), (0, 0, -1), 360).moved(
                location
            )
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Loft(Solid):
    """Part Operation: Loft

    Loft the pending sketches/faces, across all workplanes, into a solid.

    Args:
        sections (Face): sequence of loft sections. If not provided, pending_faces
            will be used.
        ruled (bool, optional): discontiguous layer tangents. Defaults to False.
        mode (Mode, optional): combination mode. Defaults to Mode.ADD.
    """

    def __init__(self, *sections: Face, ruled: bool = False, mode: Mode = Mode.ADD):

        context: BuildPart = BuildPart._get_context()

        if not sections:
            loft_wires = [face.outerWire() for face in context.pending_faces]
        else:
            loft_wires = [section.outerWire() for section in sections]
        new_solid = Solid.makeLoft(loft_wires, ruled)

        context.pending_faces = []
        context._add_to_context(new_solid, mode=mode)
        super().__init__(new_solid.wrapped)


class Revolve(Compound):
    """Part Operation: Revolve

    Revolve the profile or pending sketches/face about the given axis.

    Args:
        profile (Face, optional): 2D profile to revolve. Defaults to None.
        revolution_arc (float, optional): angular size of revolution. Defaults to 360.0.
        axis_origin (VectorLike, optional): axis start in local coordinates. Defaults to (0, 0, 0).
        axis_direction (VectorLike, optional): axis direction. Defaults to (0, 1, 0).
        mode (Mode, optional): combination mode. Defaults to Mode.ADD.

    Raises:
        ValueError: Invalid axis of revolution
    """

    def __init__(
        self,
        axis_origin: VectorLike,
        axis_direction: VectorLike,
        profile: Face = None,
        revolution_arc: float = 360.0,
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        # Make sure we account for users specifying angles larger than 360 degrees, and
        # for OCCT not assuming that a 0 degree revolve means a 360 degree revolve
        angle = revolution_arc % 360.0
        angle = 360.0 if angle == 0 else angle

        if not profile:
            profile = context.pending_faces.pop()

        axis_origin = Vector(axis_origin)
        axis_direction = Vector(axis_direction)

        # axis_origin must be on the same plane as profile
        face_occt_pln = gp_Pln(
            profile.Center().toPnt(), profile.normalAt(profile.Center()).toDir()
        )
        if not face_occt_pln.Contains(axis_origin.toPnt(), 1e-5):
            raise ValueError(
                "axis_origin must be on the same plane as the face to revolve"
            )
        if not face_occt_pln.Contains(
            gp_Lin(axis_origin.toPnt(), axis_direction.toDir()), 1e-5, 1e-5
        ):
            raise ValueError("axis must be in the same plane as the face to revolve")

        new_solid = Solid.revolve(
            profile,
            angle,
            axis_origin,
            axis_origin + axis_direction,
        )
        new_solids = [
            new_solid.moved(location)
            for location in LocationList._get_context().locations
        ]

        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Section(Compound):
    """Part Operation: Section

    Slices current part at the given height by section_by or current workplane(s).

    Args:
        section_by (Plane, optional): sequence of planes to section object.
            Defaults to None.
        height (float, optional): workplane offset. Defaults to 0.0.
        mode (Mode, optional): combination mode. Defaults to Mode.INTERSECT.
    """

    def __init__(
        self,
        *section_by: PlaneLike,
        height: float = 0.0,
        mode: Mode = Mode.INTERSECT,
    ):
        context: BuildPart = BuildPart._get_context()

        max_size = context.part.BoundingBox().DiagonalLength

        section_planes = (
            section_by if section_by else WorkplaneList._get_context().workplanes
        )
        section_planes = (
            section_planes if isinstance(section_planes, Iterable) else [section_planes]
        )
        # If the user provided named planes, convert
        section_planes = [
            section_plane
            if isinstance(section_plane, Plane)
            else Plane.named(section_plane)
            for section_plane in section_planes
        ]
        planes = [
            Face.makePlane(
                2 * max_size,
                2 * max_size,
                basePnt=plane.origin + plane.zDir * height,
                dir=plane.zDir,
            )
            for plane in section_planes
        ]

        context._add_to_context(*planes, faces_to_pending=False, mode=mode)
        super().__init__(Compound.makeCompound(planes).wrapped)


class Shell(Compound):
    """Part Operation: Shell

    Create a hollow shell from part with provided open faces.

    Args:
        openings (Face): sequence of faces to open
        thickness (float): thickness of shell - positive values shell outwards, negative inwards.
        kind (Kind, optional): edge construction option. Defaults to Kind.ARC.
        mode (Mode, optional): combination mode. Defaults to Mode.REPLACE.
    """

    def __init__(
        self,
        *openings: Face,
        thickness: float,
        kind: Kind = Kind.ARC,
        mode: Mode = Mode.REPLACE,
    ):
        context: BuildPart = BuildPart._get_context()

        new_part = context.part.shell(openings, thickness, kind=kind.name.lower())
        context._add_to_context(new_part, mode=mode)
        super().__init__(new_part.wrapped)


class Split(Compound):
    """Part Operation: Split

    Bisect part with plane and keep either top, bottom or both.

    Args:
        bisect_by (PlaneLike, optional): plane to segment part. Defaults to Plane.named("XZ").
        keep (Keep, optional): selector for which segment to keep. Defaults to Keep.TOP.
        mode (Mode, optional): combination mode. Defaults to Mode.INTERSECT.
    """

    def __init__(
        self,
        bisect_by: PlaneLike = Plane.named("XZ"),
        keep: Keep = Keep.TOP,
        mode: Mode = Mode.INTERSECT,
    ):
        context: BuildPart = BuildPart._get_context()

        bisect_plane = (
            bisect_by if isinstance(bisect_by, Plane) else Plane.named(bisect_by)
        )

        max_size = context.part.BoundingBox().DiagonalLength

        def build_cutter(keep: Keep) -> Solid:
            cutter_center = (
                Vector(-max_size, -max_size, 0)
                if keep == Keep.TOP
                else Vector(-max_size, -max_size, -2 * max_size)
            )
            return bisect_plane.fromLocalCoords(
                Solid.makeBox(2 * max_size, 2 * max_size, 2 * max_size).moved(
                    Location(cutter_center)
                )
            )

        cutters = []
        if keep == Keep.BOTH:
            cutters.append(build_cutter(Keep.TOP))
            cutters.append(build_cutter(Keep.BOTTOM))
        else:
            cutters.append(build_cutter(keep))

        context._add_to_context(*cutters, mode=mode)
        super().__init__(context.part.wrapped)


class Sweep(Compound):
    """Part Operation: Sweep

    Sweep pending sketches/faces along path.

    Args:
        sections (Union[Face, Compound]): sequence of sections to sweep
        path (Union[Edge, Wire], optional): path to follow.
            Defaults to context pending_edges.
        multisection (bool, optional): sweep multiple on path. Defaults to False.
        is_frenet (bool, optional): use freenet algorithm. Defaults to False.
        transition (Transition, optional): discontinuity handling option.
            Defaults to Transition.RIGHT.
        normal (VectorLike, optional): fixed normal. Defaults to None.
        binormal (Union[Edge, Wire], optional): guide rotation along path. Defaults to None.
        mode (Mode, optional): combination. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        *sections: Union[Face, Compound],
        path: Union[Edge, Wire] = None,
        multisection: bool = False,
        is_frenet: bool = False,
        transition: Transition = Transition.TRANSFORMED,
        normal: VectorLike = None,
        binormal: Union[Edge, Wire] = None,
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        if path is None:
            path_wire = context.pending_edges_as_wire
        else:
            path_wire = Wire.assembleEdges([path]) if isinstance(path, Edge) else path

        if sections:
            section_list = sections
        else:
            section_list = context.pending_faces
            context.pending_faces = []

        if binormal is None and normal is not None:
            binormal_mode = Vector(normal)
        elif isinstance(binormal, Edge):
            binormal_mode = Wire.assembleEdges([binormal])
        else:
            binormal_mode = binormal

        new_solids = []
        for location in LocationList._get_context().locations:
            if multisection:
                sections = [section.outerWire() for section in section_list]
                new_solid = Solid.sweep_multi(
                    sections, path_wire, True, is_frenet, binormal_mode
                ).moved(location)
            else:
                for section in section_list:
                    new_solid = Solid.sweep(
                        section,
                        path_wire,
                        True,  # make solid
                        is_frenet,
                        binormal_mode,
                        transition.name.lower(),
                    ).moved(location)
            new_solids.append(new_solid)

        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


#
# Objects
#


class Box(Compound):
    """Part Object: Box

    Create a box(es) and combine with part.

    Args:
        length (float): box size
        width (float): box size
        height (float): box size
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        centered (tuple[bool, bool, bool], optional): center about axes.
            Defaults to (True, True, True).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        length: float,
        width: float,
        height: float,
        rotation: RotationLike = (0, 0, 0),
        centered: tuple[bool, bool, bool] = (True, True, True),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        center_offset = Vector(
            -length / 2 if centered[0] else 0,
            -width / 2 if centered[1] else 0,
            -height / 2 if centered[2] else 0,
        )
        new_solids = [
            Solid.makeBox(
                length,
                width,
                height,
                center_offset,
                Vector(0, 0, 1),
            ).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Cone(Compound):
    """Part Object: Cone

    Create a cone(s) and combine with part.

    Args:
        bottom_radius (float): cone size
        top_radius (float): top size, could be zero
        height (float): cone size
        arc_size (float, optional): angular size of cone. Defaults to 360.
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        centered (tuple[bool, bool, bool], optional): center about axes.
            Defaults to (True, True, True).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        bottom_radius: float,
        top_radius: float,
        height: float,
        arc_size: float = 360,
        rotation: RotationLike = (0, 0, 0),
        centered: tuple[bool, bool, bool] = (True, True, True),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        center_offset = Vector(
            0 if centered[0] else max(bottom_radius, top_radius),
            0 if centered[1] else max(bottom_radius, top_radius),
            -height / 2 if centered[2] else 0,
        )
        new_solids = [
            Solid.makeCone(
                bottom_radius,
                top_radius,
                height,
                center_offset,
                Vector(0, 0, 1),
                arc_size,
            ).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Cylinder(Compound):
    """Part Object: Cylinder

    Create a cylinder(s) and combine with part.

    Args:
        radius (float): cylinder size
        height (float): cylinder size
        arc_size (float, optional): angular size of cone. Defaults to 360.
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        centered (tuple[bool, bool, bool], optional): center about axes.
            Defaults to (True, True, True).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        radius: float,
        height: float,
        arc_size: float = 360,
        rotation: RotationLike = (0, 0, 0),
        centered: tuple[bool, bool, bool] = (True, True, True),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()
        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        center_offset = Vector(
            0 if centered[0] else radius,
            0 if centered[1] else radius,
            -height / 2 if centered[2] else 0,
        )
        new_solids = [
            Solid.makeCylinder(
                radius,
                height,
                center_offset,
                Vector(0, 0, 1),
                arc_size,
            ).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Sphere(Compound):
    """Part Object: Sphere

    Create a sphere(s) and combine with part.

    Args:
        radius (float): sphere size
        arc_size1 (float, optional): angular size of sphere. Defaults to -90.
        arc_size2 (float, optional): angular size of sphere. Defaults to 90.
        arc_size3 (float, optional): angular size of sphere. Defaults to 360.
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        centered (tuple[bool, bool, bool], optional): center about axes.
            Defaults to (True, True, True).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        radius: float,
        arc_size1: float = -90,
        arc_size2: float = 90,
        arc_size3: float = 360,
        rotation: RotationLike = (0, 0, 0),
        centered: tuple[bool, bool, bool] = (True, True, True),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        center_offset = Vector(
            0 if centered[0] else radius,
            0 if centered[1] else radius,
            0 if centered[2] else radius,
        )
        new_solids = [
            Solid.makeSphere(
                radius,
                center_offset,
                (0, 0, 1),
                arc_size1,
                arc_size2,
                arc_size3,
            ).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Torus(Compound):
    """Part Object: Torus

    Create a torus(es) and combine with part.


    Args:
        major_radius (float): torus size
        minor_radius (float): torus size
        major_arc_size (float, optional): angular size or torus. Defaults to 0.
        minor_arc_size (float, optional): angular size or torus. Defaults to 360.
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        centered (tuple[bool, bool, bool], optional): center about axes.
            Defaults to (True, True, True).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        major_radius: float,
        minor_radius: float,
        major_arc_size: float = 0,
        minor_arc_size: float = 360,
        rotation: RotationLike = (0, 0, 0),
        centered: tuple[bool, bool, bool] = (True, True, True),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        center_offset = Vector(
            0 if centered[0] else major_radius,
            0 if centered[1] else major_radius,
            0 if centered[2] else minor_radius,
        )
        new_solids = [
            Solid.makeTorus(
                major_radius,
                minor_radius,
                center_offset,
                Vector(0, 0, 1),
                major_arc_size,
                minor_arc_size,
            ).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)


class Wedge(Compound):
    """Part Object: Wedge

    Create a wedge(s) and combine with part.

    Args:
        dx (float): distance along the X axis
        dy (float): distance along the Y axis
        dz (float): distance along the Z axis
        xmin (float): minimum X location
        zmin (float): minimum Z location
        xmax (float): maximum X location
        zmax (float): maximum Z location
        rotation (RotationLike, optional): angles to rotate about axes. Defaults to (0, 0, 0).
        mode (Mode, optional): combine mode. Defaults to Mode.ADD.
    """

    def __init__(
        self,
        dx: float,
        dy: float,
        dz: float,
        xmin: float,
        zmin: float,
        xmax: float,
        zmax: float,
        rotation: RotationLike = (0, 0, 0),
        mode: Mode = Mode.ADD,
    ):
        context: BuildPart = BuildPart._get_context()

        rotate = Rotation(*rotation) if isinstance(rotation, tuple) else rotation
        new_solids = [
            Solid.makeWedge(dx, dy, dz, xmin, zmin, xmax, zmax).moved(location * rotate)
            for location in LocationList._get_context().locations
        ]
        context._add_to_context(*new_solids, mode=mode)
        super().__init__(Compound.makeCompound(new_solids).wrapped)

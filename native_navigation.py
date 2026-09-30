"""Native navigation v43 grammar from UnPath.h / UnNavigationMesh.cpp."""
from native_reader import BoundedNativeWalker, NativeLayoutError


class NavigationWalker(BoundedNativeWalker):
    BASE_EDGES = {"FNavMeshEdgeBase", "FNavMeshBasicOneWayEdge"}
    SPECIAL_EDGES = {"FNavMeshSpecialMoveEdge", "FNavMeshMantleEdge", "FNavMeshCoverSlipEdge"}
    CROSS_EDGES = SPECIAL_EDGES | {"FNavMeshCrossPylonEdge", "FNavMeshOneWayBackRefEdge",
                                   "FNavMeshDropDownEdge", "FNavMeshPathObjectEdge"}

    def actor_reference(self):
        self.object_ref()
        self.fields([4] * 4)

    def poly_reference(self):
        self.actor_reference()
        self.fields([4])

    def combat_zone(self):
        def entry():
            self.poly_reference()
            self.fields([4])  # LinkedPolyMap value
        count = self.array(entry, 28)
        self.converter.stats["combat_zone_polys"] += count
        return self.pos

    def vertex(self):
        self.fields([4] * 3)
        self.fixed_array([2])  # PolyIndices

    def poly(self):
        self.fixed_array([2])  # PolyVerts
        self.fixed_array([2])  # PolyEdges
        self.fields([4] * 12 + [1])  # center, normal, BoxBounds

        def cover():
            self.actor_reference()
            self.fields([4])  # SlotIdx; C++ operator writes base first

        self.array(cover, 24)
        self.fields([4])  # PolyHeight

    def edge(self, name):
        cross = name in self.CROSS_EDGES
        if not cross and name not in self.BASE_EDGES:
            raise NativeLayoutError("unmodelled navigation edge class")
        self.fields([2] * (4 if cross else 2))  # verts / other-pylon verts
        self.fields([2, 2])  # Poly0 / Poly1
        self.fields([4] * 4 + [1, 1] + [4] * 3)  # length, center, type/group, perp
        if cross:
            self.poly_reference()
            self.poly_reference()
            self.fields([2])  # ObstaclePolyID
        if name in self.SPECIAL_EDGES:
            self.actor_reference()  # RelActor
            self.fields([4])  # RelItem
            self.object_ref()  # native FBasedPosition::Base
            self.fields([4] * 3)  # native FBasedPosition::Position; no tag stream
            self.fields([4])  # MoveDir
        elif name == "FNavMeshDropDownEdge":
            self.fields([4])  # DropHeight
        elif name == "FNavMeshPathObjectEdge":
            self.actor_reference()
            self.fields([4])  # InternalPathObjectID

    def walk(self):
        if self.integer() != 43:
            raise NativeLayoutError("unsupported navigation grammar version")
        self.fields([4])  # VersionAtGenerationTime
        self.array(self.vertex, 16)
        edges = []
        names = getattr(self.converter, "_names", ())

        def storage():
            self.fields([4, 2])  # allocation offset/size; constructors rebuild these on PC
            self.need(8)
            index = self.converter.i32(self.pos)
            if not 0 <= index < len(names):
                raise NativeLayoutError("invalid navigation edge class FName")
            self.fname()
            name = names[index]
            if name not in self.BASE_EDGES | self.CROSS_EDGES:
                raise NativeLayoutError("unknown navigation edge class")
            edges.append(name)

        self.array(storage, 14)
        self.array(self.poly, 65)
        self.fields([4] * 32)  # LocalToWorld / WorldToLocal
        self.fixed_array([2, 2, 2])  # BorderEdgeSegments (v43 always serialized)
        self.fields([4] * 6 + [1])  # BoxBounds
        for name in edges:
            self.edge(name)
        self.converter.stats["navigation_edges"] += len(edges)
        return self.pos

    def pylon(self):
        # DynamicObstacleMesh is transient/null during a persistent load.
        self.object_ref()
        self.object_ref()
        return self.pos

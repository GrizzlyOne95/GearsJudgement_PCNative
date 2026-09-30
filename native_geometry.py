"""v845 geometry/lighting tails, following the isolated UE3 C++ serializers."""
from native_reader import BoundedNativeWalker, NativeLayoutError


class GeometryWalker(BoundedNativeWalker):
    def flag(self):
        value = self.integer()
        if value not in (0, 1):
            raise NativeLayoutError("invalid native boolean")
        return value

    def raw_byte_bulk(self):
        position = self.converter.byte_bulk_data(self.pos, self.end)
        if position is None or position > self.end:
            raise NativeLayoutError("unsupported byte bulk data")
        self.pos = position

    def cached_convex(self):
        # PhysX blobs have their own format; only UE3 counts/header widths swap.
        self.array(lambda: self.bulk([1]), 8)

    def body_setup(self):
        self.array(self.cached_convex, 4)
        return self.pos

    def brush_component(self):
        self.cached_convex()
        return self.pos

    def light_component(self):
        def volume():
            self.fixed_array([4] * 4)
            self.fixed_array([4] * 4)
        self.array(volume, 8)
        self.array(volume, 8)
        return self.pos

    def color_buffer(self):
        stride, vertices = self.integer(), self.integer()
        if vertices < 0 or stride not in (0, 4) or (vertices and stride != 4):
            raise NativeLayoutError("invalid color buffer header")
        # No VertexData is allocated or serialized for an empty color buffer.
        if vertices and self.bulk([4]) != vertices:
            raise NativeLayoutError("color buffer count mismatch")
        return vertices

    def lightmap(self):
        kind = self.integer()
        if kind == 0:
            return
        if kind not in (1, 2):
            raise NativeLayoutError("unknown lightmap type")
        self.fixed_array([4] * 4)  # LightGuids
        if kind == 1:
            self.object_ref()  # Owner
            self.raw_byte_bulk()  # DirectionalSamples are packed BYTE coefficients
            self.fields([4] * 9)  # Three RGB scale vectors
            self.raw_byte_bulk()  # SimpleSamples are packed BYTE coefficients
        else:
            for _ in range(3):
                self.object_ref()
                self.fields([4] * 3)
            self.fields([4] * 4)  # CoordinateScale / CoordinateBias

    def instance_lod(self):
        self.array(self.object_ref, 4)  # ShadowMaps
        self.array(self.object_ref, 4)  # ShadowVertexBuffers
        self.lightmap()
        has_colors = self.byte()
        if has_colors not in (0, 1):
            raise NativeLayoutError("invalid override-color flag")
        if has_colors:
            self.color_buffer()
        self.fixed_array([4] * 5)  # PaintedVertices: vector, packed normal, color

    def static_component(self):
        self.array(self.instance_lod, 17)
        return self.pos

    def model_component(self):
        self.object_ref()  # Model
        self.fields([4])  # ZoneIndex

        def element():
            self.lightmap()
            self.object_ref()  # Component
            self.object_ref()  # Material
            self.fixed_array([2])  # Nodes
            self.array(self.object_ref, 4)  # ShadowMaps
            self.fixed_array([4] * 4)  # IrrelevantLights

        self.array(element, 24)
        self.fields([2])  # ComponentIndex
        self.fixed_array([2])  # Nodes
        return self.pos

    def model(self):
        self.fields([4] * 7)  # Bounds
        self.bulk([4] * 3)  # Vectors
        self.bulk([4] * 3)  # Points
        self.bulk([4] * 7 + [2, 2] + [4] * 5 + [1] * 4 + [4, 4])  # FBspNode, 64B
        self.object_ref()  # Surfs TTransArray owner

        def surface():
            self.object_ref()  # Material
            self.fields([4] * 6)
            self.object_ref()  # Actor
            self.fields([4] * 7)  # Plane, ShadowMapScale, LightingChannels, LightmassIndex

        self.array(surface, 60)
        self.bulk([4] * 4)  # Console FVert; runtime expands 16B disk to 24B PC
        self.fields([4])  # NumSharedSides
        zones = self.integer()
        if not 0 <= zones <= 64:
            raise NativeLayoutError("invalid BSP zone count")
        for _ in range(zones):
            self.object_ref()
            self.fields([8, 8, 4])
        self.object_ref()  # Polys
        self.bulk([4])  # LeafHulls
        self.bulk([4])  # Leaves
        self.flag()  # RootOutside
        self.flag()  # Linked
        self.bulk([4])  # PortalNodes
        self.fields([4])  # NumUniqueVertices
        self.bulk([4] * 9)  # FModelVertex: position, packed normals, UV, shadow UV
        self.fields([4] * 4)  # LightingGuid
        self.fixed_array([4] * 9)  # LightmassSettings
        return self.pos

    def shadow_map_1d(self):
        self.fixed_array([4])  # TResourceArray<FLOAT>
        self.fields([4] * 4)  # LightGuid
        return self.pos

    def decal_component(self):
        def receiver():
            self.object_ref()
            self.bulk([4] * 7)  # Position, packed tangent X/Z, float LightMapCoordinate
            self.bulk([2])  # WORD indices
            self.fields([4])  # NumTriangles
            self.lightmap()
            self.array(self.object_ref, 4)  # ShadowMap1D
            self.fields([4, 4])  # Data, InstanceIndex
        self.array(receiver, 44)
        return self.pos

    def kdop_tree(self):
        self.fields([4] * 6)
        self.bulk([1] * 6)
        self.bulk([2] * 4)

    def static_element(self):
        self.object_ref()
        self.fields([4] * 8)
        self.fixed_array([4, 4])  # FFragmentRange
        if self.byte() != 0:
            raise NativeLayoutError("unsupported PS3-specific static mesh element")

    def static_lod(self):
        # Console cooks remove RawTriangles. Populated source triangles need a
        # separate model and are deliberately rejected rather than skipped.
        self.need(16)
        flags, count, size = [self.converter.i32(self.pos + i * 4) for i in range(3)]
        if count != 0 or size != 0 or flags & ~(1 | 32):
            raise NativeLayoutError("unsupported populated static-mesh RawTriangles")
        self.fields([4] * 4)
        self.array(self.static_element, 41)
        stride, positions = self.integer(), self.integer()
        if stride != 12 or positions < 0 or self.bulk([4] * 3) != positions:
            raise NativeLayoutError("invalid static position buffer")
        uvs, stride, vertices, full_precision = [self.integer() for _ in range(4)]
        if not 1 <= uvs <= 4 or full_precision not in (0, 1):
            raise NativeLayoutError("invalid static UV layout")
        widths = [4, 4] + [4 if full_precision else 2] * (2 * uvs)
        if stride != sum(widths) or self.bulk(widths) != vertices:
            raise NativeLayoutError("invalid static tangent/UV buffer")
        colors = self.color_buffer()
        num_vertices = self.integer()
        if num_vertices != positions or num_vertices != vertices or colors not in (0, vertices):
            raise NativeLayoutError("static vertex-buffer counts disagree")
        self.bulk([2])  # IndexBuffer
        self.bulk([2])  # WireframeIndexBuffer
        self.converter.stats["static_mesh_lods"] += 1

    def static_mesh(self):
        self.fields([4] * 7)  # Bounds
        self.object_ref()  # BodySetup
        self.kdop_tree()
        self.fields([4])  # InternalVersion
        if self.flag():  # SourceData.bHaveSourceData
            self.static_lod()
        self.fixed_array([4])  # MaxDeviations
        self.flag()  # bHasBeenSimplified
        lods = self.array(self.static_lod, 89)
        # FStaticMeshLODInfo serializes its members only during memory counting;
        # the persistent TArray contains a count with zero bytes per element.
        lod_info = self.integer()
        if not 0 <= lod_info <= lods:
            raise NativeLayoutError("invalid static mesh LODInfo count")
        self.fields([4] * 4)  # ThumbnailAngle, ThumbnailDistance
        self.string()  # HighResSourceMeshName
        self.fields([4] * 6)  # HighResSourceMeshCRC, LightingGuid, VertexPositionVersionNumber
        self.fixed_array([4])  # CachedStreamingTextureFactors
        self.flag()  # bRemoveDegenerates
        return self.pos

    def fractured_mesh(self):
        self.static_mesh()
        self.object_ref()  # SourceStaticMesh

        def fragment():
            self.fields([4] * 3)  # Center
            self.fixed_array([4] * 3)  # ConvexHull.VertexData
            self.fixed_array([4] * 4)  # PermutedVertexData
            self.fixed_array([4])  # FaceTriData
            self.fixed_array([4] * 3)  # EdgeDirections
            self.fixed_array([4] * 3)  # FaceNormalDirections
            self.fixed_array([4] * 4)  # FacePlaneData
            self.fields([4] * 6 + [1])  # ElemBox
            self.fields([4] * 7)  # Bounds
            self.fixed_array([1])  # Neighbours
            for _ in range(3):
                self.flag()  # destroyable, root, never spawn physics
            self.fields([4] * 3)  # AverageExteriorNormal
            self.fixed_array([4])  # NeighbourDims

        self.array(fragment, 113)
        self.fields([4] * 14)  # two indices, scale/offset, rotation, PlaneBias
        self.fields([2, 2])  # WORD non-critical build versions
        return self.pos

    def level(self):
        self.object_ref()  # Actors TTransArray owner
        self.array(self.object_ref, 4)
        for _ in range(4):
            self.string()  # FURL Protocol, Host, Map, Portal
        self.array(self.string, 4)  # URL options
        self.fields([4, 4])  # Port, Valid
        self.object_ref()  # Model
        self.array(self.object_ref, 4)  # ModelComponents
        self.array(self.object_ref, 4)  # GameSequences

        def texture_instances():
            self.object_ref()
            self.fixed_array([4] * 5)  # sphere + texel factor

        self.array(texture_instances, 8)

        def dynamic_instance():
            self.fields([4] * 5)  # sphere + texel factor
            self.object_ref()  # Texture
            self.flag()  # bAttached
            self.fields([4])  # OriginalRadius

        def dynamic_instances():
            self.object_ref()  # Component
            self.array(dynamic_instance, 32)

        self.array(dynamic_instances, 8)
        # APEX caches of up to 16 bytes are sentinels ignored by the runtime.
        apex_size = self.integer()
        if not 0 <= apex_size <= 16:
            raise NativeLayoutError("unsupported populated APEX level cache")
        self.fields([1] * apex_size)
        self.bulk([1])  # CachedPhysBSPData

        def phys_mapping():
            self.object_ref()
            self.fields([4] * 4)  # Scale3D, CachedDataIndex

        self.array(phys_mapping, 20)
        self.array(self.cached_convex, 4)  # CachedPhysSMDataStore
        self.array(phys_mapping, 20)
        self.array(lambda: self.bulk([1]), 8)  # CachedPhysPerTriSMDataStore
        self.fields([4, 4])  # cache versions

        def force_texture():
            self.object_ref()
            self.flag()

        self.array(force_texture, 8)
        self.cached_convex()  # CachedPhysConvexBSPData
        self.fields([4])  # CachedPhysConvexBSPVersion
        for _ in range(6):
            self.object_ref()  # Nav / Cover / Pylon start+end
        self.fixed_array([4] * 5)  # CrossLevelCoverGuidRefs
        self.array(self.object_ref, 4)  # CoverLinkRefs
        self.fixed_array([4, 1])  # CoverIndexPairs
        self.array(self.object_ref, 4)  # CrossLevelActors
        if self.flag():  # PrecomputedLightVolume initialized
            self.fields([4] * 6 + [1])  # FBox bounds
            self.fields([4])  # SampleSpacing
            self.fixed_array([4] * 4 + [1] * 4 + [4] * 3 + [1])
        self.fields([4] * 6)  # visibility origin, cell and bucket sizes/count

        def visibility_chunk():
            self.flag()  # bCompressed
            if self.integer() < 0:
                raise NativeLayoutError("negative visibility decompressed size")
            self.fixed_array([1])  # zlib bytes are endian-neutral

        def visibility_bucket():
            if self.integer() < 0:
                raise NativeLayoutError("negative visibility cell size")
            self.fixed_array([4, 4, 4, 2, 2])  # cell Min, ChunkIndex, DataOffset
            self.array(visibility_chunk, 12)

        self.array(visibility_bucket, 12)
        self.fields([4])  # VolumeMaxDistance
        self.fields([4] * 6 + [1])  # VolumeBox
        self.fields([4] * 3)  # VolumeSizeX/Y/Z
        self.fixed_array([4])  # FColor.DWColor(), not individual byte properties
        return self.pos

    def collection(self, property_name):
        count = getattr(self.converter, "_native_array_counts", {}).get(property_name)
        if count is None or count < 0 or self.end - self.pos != count * 64:
            raise NativeLayoutError("collection matrix count disagrees with component array")
        for _ in range(count):
            self.fields([4] * 16)
        return self.pos
